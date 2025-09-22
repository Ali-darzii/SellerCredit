from django.urls import path

from authentication.api.v1 import authentication


urlpatterns = [
    path('token/', authentication.TokenObtain.as_view(), name='token_obtain_pair'),
    path('token/block', authentication.BlacklistToken.as_view(), name='token_blacklist'),
    path('token/verify', authentication.TokenVerify.as_view(), name='token_verify'),
    path('token/refresh/', authentication.RefreshToken.as_view(), name='token_refresh'),
]