import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class JSONOnlyMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if 'application/json' not in request.META.get('HTTP_ACCEPT', ''):
            request.META['HTTP_ACCEPT'] = 'application/json'
        return None
    
    def process_response(self, request, response):
        if isinstance(response, JsonResponse):
            return response

        status_code = response.status_code
        if 200 <= status_code < 300:
            return response
        
        status_message = self._get_fancy_status_message(status_code)
        try:
            if hasattr(response, 'content') and response.content:
                try:
                    content = json.loads(response.content)
                except (json.JSONDecodeError, ValueError):
                    content = response.content.decode('utf-8', errors='ignore')
            else:
                content = None
            
            json_data = {
                "status": status_message,
                "status_code": status_code,
                "success": False,
                "meta": {
                    "path": request.path,
                    "method": request.method,
                    "timestamp": self._get_timestamp()
                }
            }
            
            return JsonResponse(
                json_data,
                status=status_code,
                safe=False,
                json_dumps_params={'indent': 2}
            )
            
        except Exception as e:
            return JsonResponse({
                "status": "🔥 Something went terribly wrong",
                "status_code": 500,
                "success": False,
                "error": str(e),
                "meta": {
                    "path": request.path,
                    "method": request.method,
                    "timestamp": self._get_timestamp()
                }
            }, status=500)
    
    def process_exception(self, request, exception):
        return JsonResponse({
            "status": "💥 Epic failure detected",
            "status_code": 500,
            "success": False,
            "error": {
                "type": exception.__class__.__name__,
                "message": str(exception),
                "details": "Check your server logs for more information"
            },
            "meta": {
                "path": request.path,
                "method": request.method,
                "timestamp": self._get_timestamp()
            }
        }, status=500)
    
    def _get_fancy_status_message(self, status_code):
        status_messages = {
            200: "✨ Mission accomplished",
            201: "🎉 Created successfully",
            202: "👍 Accepted and processing",
            204: "✅ Success with no content",

            301: "🚚 Moved permanently",
            302: "🔀 Found elsewhere",
            304: "💾 Not modified, use cache",
            
            400: "🤔 Bad request, check your input",
            401: "🔐 Authentication required",
            403: "🚫 Access forbidden",
            404: "🕵️ Not found in our universe",
            405: "⛔ Method not allowed",
            408: "⏰ Request timeout",
            409: "⚔️ Conflict detected",
            410: "👻 Gone forever",
            422: "🧩 Unprocessable entity",
            429: "🐌 Too many requests, slow down",
            
            500: "💔 Internal server error",
            501: "🚧 Not implemented yet",
            502: "🔌 Bad gateway",
            503: "😴 Service unavailable",
            504: "⏳ Gateway timeout",
        }

        if status_code in status_messages:
            return status_messages[status_code]
        elif 200 <= status_code < 300:
            return f"✨ Success ({status_code})"
        elif 300 <= status_code < 400:
            return f"🔀 Redirect ({status_code})"
        elif 400 <= status_code < 500:
            return f"🤷 Client error ({status_code})"
        else:
            return f"💥 Server error ({status_code})"
    
    def _get_timestamp(self):
        from datetime import datetime
        return datetime.utcnow().isoformat() + 'Z'


class SimpleJSONMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if not isinstance(response, JsonResponse):
            try:
                content = json.loads(response.content) if response.content else {}
            except (json.JSONDecodeError, ValueError):
                content = {"message": response.content.decode('utf-8', errors='ignore')}
            
            return JsonResponse({
                "status": response.status_code,
                "data": content
            }, status=response.status_code)
        
        return response