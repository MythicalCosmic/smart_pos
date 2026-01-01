import jwt
from functools import wraps
from django.conf import settings
from rest_framework.response import Response  
from rest_framework import status 
from main.models import User, Session

JWT_SECRET = getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)
JWT_ALGO = "HS256"

def user_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = request.headers.get("Authorization")

        if not token:
            return Response(
                {"message": "Missing token"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

        if token.startswith("Bearer "):
            token = token.split(" ")[1]
            
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        except jwt.ExpiredSignatureError:
            return Response(
                {"message": "Token expired"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
        except jwt.InvalidTokenError:
            return Response(
                {"message": "Invalid token"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
            
        user_id = payload.get("user_id")

        try:
            user = User.objects.only("id", "role", "status").get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if not Session.objects.filter(user_id=user_id, payload=token[:20]).exists():
            return Response(
                {"message": "Session expired"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

        # ✅ IMPORTANT: Set request.user for DRF
        request.user = user
        request._dont_enforce_csrf_checks = True  # Skip CSRF for API
        
        return view_func(request, *args, **kwargs)

    return wrapper