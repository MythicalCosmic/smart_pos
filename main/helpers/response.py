from django.http import JsonResponse


class APIResponse:
    
    @staticmethod
    def success(data=None, message="Success", status_code=200, meta=None):
        response = {
            "success": True,
            "message": message,
            "data": data
        }
        if meta:
            response["meta"] = meta
        return JsonResponse(response, status=status_code)
    
    @staticmethod
    def error(message="Error occurred", errors=None, status_code=400, data=None):
        response = {
            "success": False,
            "message": message
        }
        if errors:
            response["errors"] = errors
        if data:
            response["data"] = data
        return JsonResponse(response, status=status_code)
    
    @staticmethod
    def created(data=None, message="Created successfully", status_code=201):
        return APIResponse.success(data=data, message=message, status_code=status_code)
    
    @staticmethod
    def unauthorized(message="Unauthorized access"):
        return APIResponse.error(message=message, status_code=401)
    
    @staticmethod
    def forbidden(message="Access forbidden"):
        return APIResponse.error(message=message, status_code=403)
    
    @staticmethod
    def not_found(message="Resource not found"):
        return APIResponse.error(message=message, status_code=404)
    
    @staticmethod
    def validation_error(errors, message="Validation failed"):
        return APIResponse.error(message=message, errors=errors, status_code=422)
    
    @staticmethod
    def server_error(message="Internal server error"):
        return APIResponse.error(message=message, status_code=500)