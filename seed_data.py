#!/usr/bin/env python3
"""
1000 öğrenci için CLOUD101 not verisi ekler.
Kullanım: python3 seed_data.py
Ayrıca benchmark için students.csv dosyası üretir.
"""

import boto3
import csv
import os
import uuid

REGION       = os.getenv("AWS_REGION", "us-east-1")
GRADES_TABLE = os.getenv("GRADES_TABLE", "GradeRelease-Grades")
STUDENT_COUNT = 1000
COURSE_CODE   = "CLOUD101"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table    = dynamodb.Table(GRADES_TABLE)

def seed():
    student_ids = []
    print(f"Seeding {STUDENT_COUNT} students...")

    with table.batch_writer() as batch:
        for i in range(1, STUDENT_COUNT + 1):
            student_id = f"S-{100000 + i}"
            username   = f"student{i}"
            student_ids.append(student_id)

            for grade_item, score in [("midterm", 50 + (i % 51)), ("final", 60 + (i % 41))]:
                batch.put_item(Item={
                    "pk":               f"GRADE#{COURSE_CODE}#{student_id}",
                    "sk":               grade_item,
                    "course_code":      COURSE_CODE,
                    "grade_item":       grade_item,
                    "student_id":       student_id,
                    "student_username": username,
                    "score":            str(score),
                    "request_id":       str(uuid.uuid4()),
                })

            if i % 100 == 0:
                print(f"  {i}/{STUDENT_COUNT} öğrenci eklendi...")

    print(f"✅ {STUDENT_COUNT} öğrenci eklendi.")

    # k6 için students.csv oluştur
    csv_path = "benchmark/students.csv"
    os.makedirs("benchmark", exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id"])
        for sid in student_ids:
            writer.writerow([sid])
    print(f"✅ {csv_path} oluşturuldu ({STUDENT_COUNT} satır)")

if __name__ == "__main__":
    seed()
