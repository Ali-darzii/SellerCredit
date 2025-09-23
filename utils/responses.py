class ErrorResponses:
    OBJECT_NOT_FOUND = {"detail": "Object not found.", "status_code": 0}
    BAD_FORMAT = {"detail": "Bad foramt request.", "status_code": 1}
    IDEMPOTENCY = {"detail": "Request with this Idempotency-Key already processed", "status_code": 2}
    PERMISSION_DENIED = {"detail": "you don't have permission to make action.", "status_code": 3}
    SOMTHING_WENT_WRONG = {"detail":"Somthing went wrong.", "status_code": 4}