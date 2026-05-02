#!/usr/bin/env python3
"""
DynamoDB tablolarını ve SNS topic'ini oluşturur.
Çalıştırmadan önce: aws configure (veya EC2 IAM role ile)
Kullanım: python3 setup_aws.py
"""

import boto3
import os

REGION    = os.getenv("AWS_REGION", "us-east-1")
TEAM_ID   = "team-3"
STAGE     = "stage1"

dynamodb = boto3.client("dynamodb", region_name=REGION)
sns      = boto3.client("sns", region_name=REGION)

TAGS = [
    {"Key": "Project",   "Value": "GradeRelease"},
    {"Key": "Team",      "Value": TEAM_ID},
    {"Key": "Stage",     "Value": STAGE},
    {"Key": "Benchmark", "Value": "official"},
]

def create_table(name, pk, sk=None):
    attr_defs = [{"AttributeName": pk, "AttributeType": "S"}]
    key_schema = [{"AttributeName": pk, "KeyType": "HASH"}]
    if sk:
        attr_defs.append({"AttributeName": sk, "AttributeType": "S"})
        key_schema.append({"AttributeName": sk, "KeyType": "RANGE"})
    try:
        dynamodb.create_table(
            TableName=name,
            AttributeDefinitions=attr_defs,
            KeySchema=key_schema,
            BillingMode="PAY_PER_REQUEST",
            Tags=TAGS,
        )
        print(f"✅ Tablo oluşturuldu: {name}")
    except dynamodb.exceptions.ResourceInUseException:
        print(f"ℹ️  Tablo zaten var: {name}")

def create_sns_topic():
    resp = sns.create_topic(
        Name="GradeRelease-Notifications",
        Tags=TAGS,
    )
    arn = resp["TopicArn"]
    print(f"✅ SNS Topic: {arn}")
    print(f"\n⚠️  Bu ARN'ı .env dosyasındaki SNS_TOPIC_ARN değerine yapıştır:\n{arn}")
    return arn

if __name__ == "__main__":
    print("─── DynamoDB Tabloları oluşturuluyor ───")
    # Grades tablosu: pk = GRADE#COURSE#STUDENT veya IDEM#REQUEST_ID
    create_table("GradeRelease-Grades", pk="pk", sk="sk")
    # Courses tablosu: pk = course_code
    create_table("GradeRelease-Courses", pk="course_code")
    print("\n─── SNS Topic oluşturuluyor ───")
    create_sns_topic()
    print("\n✅ Kurulum tamamlandı!")
