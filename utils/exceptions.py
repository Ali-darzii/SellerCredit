from rest_framework.exceptions import APIException


class CookieException(APIException):
    status_code = 500
    default_detail = 'Error in setting cookie in server'
    default_code = 'set_cookie_error'