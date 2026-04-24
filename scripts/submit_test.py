
curl -k -X POST "http://localhost:8080/api/method/tap_lms.imgana.submission.assignment_submission_internal" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "qwqWwre12@321",
    "assign_id": "fun-faces-1313",
    "name1": "Test_Hindi",
    "glific_id": "1234",
    "submission": "https://storage.googleapis.com/tap-lms-submissions/submissions/submissions_IMSUB.png"
}'


curl -k -X POST "http://localhost:8080/api/method/tap_lms.imgana.submission.assignment_submission_internal" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "qwqWwre12@321",
    "assign_id": "fun-faces-1313",
    "name1": "Test_Hindi",
    "glific_id": "1234",
    "submission": "HELLO WHO ARE YOU?"
}'

curl -k -X POST "http://localhost:8080/api/method/tap_lms.imgana.submission.assignment_submission_internal" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "qwqWwre12@321",
    "assign_id": "fun-faces-1313",
    "name1": "Test_Hindi",
    "glific_id": "1234",
    "submission": "HELLO WHO ARE YOU? 😃😃😃😃🔪"
}'


curl -k -X POST "http://localhost:8080/api/method/tap_lms.imgana.submission.assignment_submission_internal" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "qwqWwre12@321",
    "assign_id": "fun-faces-1313",
    "name1": "Test_Hindi",
    "glific_id": "1234",
    "submission": "😃😃😃😃🔪"
}'

curl -k -X POST "http://localhost:8080/api/method/tap_lms.imgana.submission.assignment_submission_internal" \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "qwqWwre12@321",
    "assign_id": "fun-faces-1313",
    "name1": "Test_Hindi",
    "glific_id": "1234",
    "submission": "😃😃😃😃Hello"
}'