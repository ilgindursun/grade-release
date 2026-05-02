import http from "k6/http";
import { check } from "k6";
import { SharedArray } from "k6/data";
import papaparse from "https://jslib.k6.io/papaparse/5.1.1/index.js";

const BASE_URL = __ENV.BASE_URL || "http://localhost:80";
const COURSE_CODE = __ENV.COURSE_CODE || "CLOUD101";
const STUDENT_FILE = __ENV.STUDENT_FILE || "benchmark/students.csv";

const students = new SharedArray("students", function () {
  const raw = open(STUDENT_FILE);
  return papaparse.parse(raw, { header: true }).data.map((r) => r.student_id).filter(Boolean);
});

export const options = {
  timeUnit: "1m",
  preAllocatedVUs: 120,
  maxVUs: 300,
  scenarios: {
    demo_load: { executor: "constant-arrival-rate", rate: 1800, duration: "6m", preAllocatedVUs: 120, maxVUs: 300 },
  },
};

export default function () {
  const idx = (__VU * __ITER) % students.length;
  const student_id = students[idx];
  const url = `${BASE_URL}/students/${student_id}/grades?course_code=${COURSE_CODE}`;
  const res = http.get(url);
  check(res, { "status 200": (r) => r.status === 200 });
}
