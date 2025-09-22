from django.shortcuts import render
from logging import getLogger
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView

from utils.exceptions import CookieException

logger = getLogger("django")


class TokenObtain(TokenObtainPairView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        response = super().post(request, *args, **kwargs)

        ref_token = response.data.get("refresh", None)
        if not ref_token:
            raise CookieException

        response.set_cookie("refresh", ref_token, httponly=True, secure=request.is_secure())
        return response

class TokenVerify(APIView):
    """Verify if your `JWT Token` is valid or not"""
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        resp = Response({"vlid": True})
        return resp


class RefreshToken(TokenRefreshView):
    def post(self, request: Request, *args, **kwargs) -> Response:
        try:
            ref_token = request.COOKIES.get("refresh", None)
            if not ref_token:
                raise CookieException
            request.data["refresh"] = ref_token

            response = super().post(request, *args, **kwargs)
            ref_token = response.data.get("refresh", None)
            if not ref_token:
                raise CookieException
            response.set_cookie("refresh", ref_token, httponly=True, secure=request.is_secure())
            return response 
        except Exception as e:
            logger.error(e, exc_info=True)
            return Response({"error": "error"}, status=status.HTTP_400_BAD_REQUEST)


class BlacklistToken(TokenBlacklistView):
    def post(self, request: Request, *args, **kwargs):
        try:
            ref_token = request.COOKIES.get("refresh", None)
            if not ref_token:
                raise CookieException
            request.data["refresh"] = ref_token
            response = super().post(request, *args, **kwargs)

            return response

        except Exception as e:
            logger.error(e, exc_info=True)
            return Response({"error": "error", "message": str(e, exc_info=True)}, status=status.HTTP_400_BAD_REQUEST)