from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, timezone
import boto3
import os
from botocore.exceptions import ClientError

app = FastAPI()

# ── Config ──────────────────────────────────────────────────────────────────
STAGE         = os.getenv("STAGE", "stage1")
TEAM_ID       = os.getenv("TEAM_ID", "team-3")
CHALLENGE     = os.getenv("CHALLENGE_CODE", "XXXX")     # ← challenge code gelince değiştir
TEAM_MEMBERS  = ["dursuni", "acikelc", "saribiyiko"]
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")
GRADES_TABLE  = os.getenv("GRADES_TABLE", "GradeRelease-Grades")
COURSES_TABLE = os.getenv("COURSES_TABLE", "GradeRelease-Courses")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
sns      = boto3.client("sns", region_name=AWS_REGION)

grades_table  = dynamodb.Table(GRADES_TABLE)
courses_table = dynamodb.Table(COURSES_TABLE)

# ── Helpers ──────────────────────────────────────────────────────────────────
def base_response():
    return {"team_id": TEAM_ID, "challenge_code": CHALLENGE}

# ── Schemas ──────────────────────────────────────────────────────────────────
class GradeRequest(BaseModel):
    course_code: str
    grade_item: str
    student_id: str
    student_username: Optional[str] = None
    score: float
    request_id: str

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("score must be between 0 and 100")
        return v

class FinalizeRequest(BaseModel):
    request_id: str
    notify: bool = True

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "ok": True,
        "stage": STAGE,
        "team_id": TEAM_ID,
        "team_members": TEAM_MEMBERS,
        "challenge_code": CHALLENGE,
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@app.post("/grades")
def enter_grade(req: GradeRequest):
    # 1) Idempotency — aynı request_id daha önce işlendiyse aynı sonucu dön
    try:
        idem = grades_table.get_item(Key={"pk": f"IDEM#{req.request_id}", "sk": "IDEM"})
        if "Item" in idem:
            item = idem["Item"]
            return {**base_response(), **{k: item[k] for k in
                    ["status","course_code","grade_item","student_id","student_username","request_id"]
                    if k in item}}
    except ClientError as e:
        raise HTTPException(500, detail=str(e))

    # 2) Kurs finalize edilmiş mi?
    try:
        course = courses_table.get_item(Key={"course_code": req.course_code})
        if course.get("Item", {}).get("finalized"):
            raise HTTPException(409, detail="Course is already finalized")
    except HTTPException:
        raise
    except ClientError as e:
        raise HTTPException(500, detail=str(e))

    # 3) Aynı mantıksal anahtar var mı? (course_code, student_id, grade_item)
    grade_pk = f"GRADE#{req.course_code}#{req.student_id}"
    grade_sk = req.grade_item
    existing = grades_table.get_item(Key={"pk": grade_pk, "sk": grade_sk})
    status = "updated" if "Item" in existing else "stored"

    # 4) Notu kaydet
    grades_table.put_item(Item={
        "pk": grade_pk,
        "sk": grade_sk,
        "course_code": req.course_code,
        "grade_item": req.grade_item,
        "student_id": req.student_id,
        "student_username": req.student_username or "",
        "score": str(req.score),
        "request_id": req.request_id,
    })

    # 5) Idempotency kaydını sakla
    idem_item = {
        "pk": f"IDEM#{req.request_id}",
        "sk": "IDEM",
        "status": status,
        "course_code": req.course_code,
        "grade_item": req.grade_item,
        "student_id": req.student_id,
        "student_username": req.student_username or "",
        "request_id": req.request_id,
    }
    grades_table.put_item(Item=idem_item)

    return {
        **base_response(),
        "status": status,
        "course_code": req.course_code,
        "grade_item": req.grade_item,
        "student_id": req.student_id,
        "student_username": req.student_username or "",
        "request_id": req.request_id,
    }


@app.get("/students/{student_id}/grades")
def get_grades(student_id: str, course_code: str = Query(...)):
    pk = f"GRADE#{course_code}#{student_id}"
    try:
        resp = grades_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(pk)
        )
    except ClientError as e:
        raise HTTPException(500, detail=str(e))

    if not resp["Items"]:
        raise HTTPException(404, detail="No grades found")

    grades = [{"grade_item": i["sk"], "score": float(i["score"])} for i in resp["Items"]]
    username = resp["Items"][0].get("student_username", "")

    return {
        **base_response(),
        "student_id": student_id,
        "student_username": username,
        "course_code": course_code,
        "grades": grades,
    }


@app.post("/courses/{course_code}/finalize")
def finalize_course(course_code: str, req: FinalizeRequest):
    # 1) Mevcut kurs durumunu al
    try:
        resp = courses_table.get_item(Key={"course_code": course_code})
    except ClientError as e:
        raise HTTPException(500, detail=str(e))

    item = resp.get("Item")

    # 2) Zaten finalize mi?
    if item and item.get("finalized"):
        # Aynı request_id → idempotent döndür
        if item.get("request_id") == req.request_id:
            return {
                **base_response(),
                "status": "finalized",
                "course_code": course_code,
                "request_id": req.request_id,
                "notification_mode": "sns-publish-only",
            }
        # Farklı request_id → already_finalized, bildirim yok
        return {
            **base_response(),
            "status": "already_finalized",
            "course_code": course_code,
            "request_id": req.request_id,
            "notification_mode": "sns-publish-only",
        }

    # 3) Finalize et ve kaydet
    courses_table.put_item(Item={
        "course_code": course_code,
        "finalized": True,
        "request_id": req.request_id,
        "finalized_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })

    # 4) SNS bildirimi gönder
    if req.notify and SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject=f"Grade Release: {course_code}",
                Message=f"Grades for {course_code} have been finalized. team_id={TEAM_ID}",
            )
        except ClientError as e:
            # SNS hatası finalize işlemini engellemez, sadece loglanır
            print(f"SNS publish error: {e}")

    return {
        **base_response(),
        "status": "finalized",
        "course_code": course_code,
        "request_id": req.request_id,
        "notification_mode": "sns-publish-only",
    }

# Lambda handler
from mangum import Mangum
handler = Mangum(app)
