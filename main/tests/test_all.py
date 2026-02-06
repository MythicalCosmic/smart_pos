import requests
import json
import random
import string
from datetime import datetime

BASE_URL = "http://localhost:8000/"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestRunner:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.passed = 0
        self.failed = 0
        self.results = []
        self.created_users = []
        self.created_categories = []
    
    def log(self, message, color=Colors.RESET):
        print(f"{color}{message}{Colors.RESET}")
    
    def log_test(self, name, passed, message=""):
        if passed:
            self.passed += 1
            self.log(f"  ✓ {name}", Colors.GREEN)
        else:
            self.failed += 1
            self.log(f"  ✗ {name}: {message}", Colors.RED)
        self.results.append({'name': name, 'passed': passed, 'message': message})
    
    def random_string(self, length=8):
        return ''.join(random.choices(string.ascii_lowercase, k=length))
    
    def request(self, method, endpoint, data=None, params=None):
        url = f"{self.base_url}{endpoint}"
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, timeout=10)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, params=params, timeout=10)
            else:
                return None
            
            return {
                'status': response.status_code,
                'data': response.json() if response.content else {},
                'success': response.status_code < 400
            }
        except Exception as e:
            return {'status': 0, 'data': {}, 'success': False, 'error': str(e)}
    
    def run_all(self):
        self.log(f"\n{'='*60}", Colors.BOLD)
        self.log("  SMART POS API TEST SUITE", Colors.BOLD)
        self.log(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", Colors.BLUE)
        self.log(f"{'='*60}\n", Colors.BOLD)
        
        self.test_user_service()
        self.test_category_service()
        self.test_role_service()
        
        self.cleanup()
        self.print_summary()
    
    def test_user_service(self):
        self.log("\n📦 USER SERVICE TESTS", Colors.BOLD)
        self.log("-" * 40)
        
        first_name = self.random_string()
        last_name = self.random_string()
        
        res = self.request('POST', '/users/create', {
            'first_name': first_name,
            'last_name': last_name,
            'password': 'test1234',
            'role': 'CASHIER'
        })
        self.log_test(
            "Create user (auto-email)",
            res['success'] and 'user' in res['data'],
            res['data'].get('message', '')
        )
        
        user_id = None
        username = None
        if res['success'] and 'user' in res['data']:
            user_id = res['data']['user']['id']
            username = res['data']['user'].get('username')
            self.created_users.append(user_id)
            
            self.log_test(
                "Auto-generated email format",
                '@smart.pos' in res['data']['user'].get('email', ''),
                f"Email: {res['data']['user'].get('email')}"
            )
            
            self.log_test(
                "Username extracted correctly",
                username and '.' in username,
                f"Username: {username}"
            )
        
        res = self.request('POST', '/users/create', {
            'first_name': '',
            'last_name': 'Test',
            'password': '1234'
        })
        self.log_test(
            "Create user validation (empty first_name)",
            not res['success'],
            res['data'].get('message', '')
        )
        
        res = self.request('POST', '/users/create', {
            'first_name': 'Test',
            'last_name': 'User',
            'password': '12'
        })
        self.log_test(
            "Create user validation (short password)",
            not res['success'],
            res['data'].get('message', '')
        )
        
        if user_id:
            res = self.request('GET', f'/users/{user_id}')
            self.log_test(
                "Get user by ID",
                res['success'] and res['data'].get('id') == user_id,
                res['data'].get('message', '')
            )
        
        if username:
            res = self.request('GET', f'/users/username/{username}')
            self.log_test(
                "Get user by username",
                res['success'],
                res['data'].get('message', '')
            )
        
        res = self.request('GET', '/users/999999')
        self.log_test(
            "Get non-existent user returns 404",
            res['status'] == 404,
            f"Status: {res['status']}"
        )
        
        res = self.request('GET', '/users', params={'page': 1, 'per_page': 10})
        self.log_test(
            "List users with pagination",
            res['success'] and 'users' in res['data'] and 'pagination' in res['data'],
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/users', params={'role': 'CASHIER'})
        self.log_test(
            "List users filtered by role",
            res['success'],
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/users', params={'search': first_name})
        self.log_test(
            "Search users",
            res['success'] and len(res['data'].get('users', [])) > 0,
            f"Found: {len(res['data'].get('users', []))}"
        )
        
        if user_id:
            new_first = self.random_string()
            res = self.request('PATCH', f'/users/{user_id}/update', {
                'first_name': new_first
            })
            self.log_test(
                "Update user first_name",
                res['success'],
                res['data'].get('message', '')
            )
            
            if res['success']:
                self.log_test(
                    "Email regenerated after name change",
                    new_first.lower() in res['data'].get('user', {}).get('email', '').lower(),
                    f"New email: {res['data'].get('user', {}).get('email')}"
                )
        
        if user_id:
            res = self.request('PATCH', f'/users/{user_id}/status', {'status': 'SUSPENDED'})
            self.log_test(
                "Update user status",
                res['success'],
                res['data'].get('message', '')
            )
            
            res = self.request('PATCH', f'/users/{user_id}/status', {'status': 'ACTIVE'})
        
        if user_id:
            res = self.request('PATCH', f'/users/{user_id}/role', {'role': 'ADMIN'})
            self.log_test(
                "Update user role",
                res['success'],
                res['data'].get('message', '')
            )
        
        if user_id:
            res = self.request('POST', f'/users/{user_id}/reset-password', {
                'new_password': 'newpass123'
            })
            self.log_test(
                "Reset password",
                res['success'],
                res['data'].get('message', '')
            )
        
        res = self.request('GET', '/users/preview-username', params={
            'first_name': 'John',
            'last_name': 'Doe'
        })
        self.log_test(
            "Preview username",
            res['success'] and 'username' in res['data'],
            f"Username: {res['data'].get('username')}"
        )
        
        res = self.request('GET', '/users/check-username', params={'username': 'nonexistent.user123'})
        self.log_test(
            "Check username availability",
            res['success'] and res['data'].get('available') == True,
            f"Available: {res['data'].get('available')}"
        )
        
        res = self.request('GET', '/users/stats')
        self.log_test(
            "Get user stats",
            res['success'] and 'total_users' in res['data'],
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/users/cashiers')
        self.log_test(
            "Get cashiers",
            res['success'] and 'users' in res['data'],
            f"Count: {res['data'].get('count', 0)}"
        )
        
        res = self.request('GET', '/users/search', params={'q': 'test', 'limit': 5})
        self.log_test(
            "Search users endpoint",
            res['success'],
            f"Found: {len(res['data'].get('users', []))}"
        )
        
        if user_id:
            res = self.request('DELETE', f'/users/{user_id}/delete')
            self.log_test(
                "Soft delete user",
                res['success'],
                res['data'].get('message', '')
            )
            
            res = self.request('GET', f'/users/{user_id}')
            self.log_test(
                "Deleted user not found in normal query",
                res['status'] == 404,
                f"Status: {res['status']}"
            )
            
            res = self.request('GET', f'/users/{user_id}', params={'include_deleted': 'true'})
            self.log_test(
                "Deleted user found with include_deleted",
                res['success'],
                res['data'].get('message', '')
            )
            
            res = self.request('POST', f'/users/{user_id}/restore')
            self.log_test(
                "Restore deleted user",
                res['success'],
                res['data'].get('message', '')
            )
        
        users_to_bulk = []
        for i in range(3):
            res = self.request('POST', '/users/create', {
                'first_name': f'Bulk{self.random_string()}',
                'last_name': f'Test{i}',
                'password': 'test1234'
            })
            if res['success']:
                users_to_bulk.append(res['data']['user']['id'])
                self.created_users.append(res['data']['user']['id'])
        
        if len(users_to_bulk) >= 2:
            res = self.request('POST', '/users/bulk/status', {
                'user_ids': users_to_bulk,
                'status': 'SUSPENDED'
            })
            self.log_test(
                "Bulk update status",
                res['success'],
                f"Updated: {res['data'].get('updated_count', 0)}"
            )
            
            res = self.request('POST', '/users/bulk/delete', {
                'user_ids': users_to_bulk
            })
            self.log_test(
                "Bulk delete",
                res['success'],
                f"Deleted: {res['data'].get('deleted_count', 0)}"
            )
            
            res = self.request('POST', '/users/bulk/restore', {
                'user_ids': users_to_bulk
            })
            self.log_test(
                "Bulk restore",
                res['success'],
                f"Restored: {res['data'].get('restored_count', 0)}"
            )
    
    def test_category_service(self):
        self.log("\n📦 CATEGORY SERVICE TESTS", Colors.BOLD)
        self.log("-" * 40)
        
        cat_name = f"Test Category {self.random_string()}"
        res = self.request('POST', '/categories/create', {
            'name': cat_name,
            'description': 'Test description',
            'status': 'ACTIVE'
        })
        self.log_test(
            "Create category",
            res['success'] and 'category' in res['data'],
            res['data'].get('message', '')
        )
        
        cat_id = None
        if res['success'] and 'category' in res['data']:
            cat_id = res['data']['category']['id']
            self.created_categories.append(cat_id)
            
            self.log_test(
                "Auto-generated slug",
                res['data']['category'].get('slug') is not None,
                f"Slug: {res['data']['category'].get('slug')}"
            )
        
        res = self.request('POST', '/categories/create', {'name': ''})
        self.log_test(
            "Create category validation (empty name)",
            not res['success'],
            res['data'].get('message', '')
        )
        
        if cat_id:
            res = self.request('GET', f'/categories/{cat_id}')
            self.log_test(
                "Get category by ID",
                res['success'],
                res['data'].get('message', '')
            )
        
        res = self.request('GET', '/categories/', params={'page': 1, 'per_page': 10})
        self.log_test(
            "List categories with pagination",
            res['success'] and 'categories' in res['data'],
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/categories/', params={'status': 'ACTIVE'})
        self.log_test(
            "List categories filtered by status",
            res['success'],
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/categories/active')
        self.log_test(
            "Get active categories",
            res['success'],
            res['data'].get('message', '')
        )
        
        if cat_id:
            new_name = f"Updated {self.random_string()}"
            res = self.request('PATCH', f'/categories/{cat_id}/update', {
                'name': new_name
            })
            self.log_test(
                "Update category name",
                res['success'],
                res['data'].get('message', '')
            )
        
        if cat_id:
            res = self.request('PATCH', f'/categories/{cat_id}/status', {'status': 'INACTIVE'})
            self.log_test(
                "Update category status",
                res['success'],
                res['data'].get('message', '')
            )
        
        res = self.request('GET', '/categories/stats')
        self.log_test(
            "Get category stats",
            res['success'] and 'total_categories' in res['data'],
            res['data'].get('message', '')
        )
        
        if cat_id:
            res = self.request('DELETE', f'/categories/{cat_id}/delete')
            self.log_test(
                "Soft delete category",
                res['success'],
                res['data'].get('message', '')
            )
            
            res = self.request('GET', f'/categories/{cat_id}')
            self.log_test(
                "Deleted category not found",
                res['status'] == 404,
                f"Status: {res['status']}"
            )
            
            res = self.request('POST', f'/categories/{cat_id}/restore')
            self.log_test(
                "Restore category",
                res['success'],
                res['data'].get('message', '')
            )
        
        res = self.request('GET', '/categories/deleted')
        self.log_test(
            "Get deleted categories",
            res['success'],
            res['data'].get('message', '')
        )
    
    def test_role_service(self):
        self.log("\n📦 ROLE SERVICE TESTS", Colors.BOLD)
        self.log("-" * 40)
        
        res = self.request('GET', '/roles/')
        self.log_test(
            "List all roles",
            res['success'] and 'roles' in res['data'],
            f"Count: {res['data'].get('count', 0)}"
        )
        
        res = self.request('GET', '/roles/ADMIN')
        self.log_test(
            "Get ADMIN role",
            res['success'] and res['data'].get('code') == 'ADMIN',
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/roles/CASHIER')
        self.log_test(
            "Get CASHIER role",
            res['success'] and res['data'].get('code') == 'CASHIER',
            res['data'].get('message', '')
        )
        
        res = self.request('GET', '/roles/INVALID_ROLE')
        self.log_test(
            "Get invalid role returns 404",
            res['status'] == 404,
            f"Status: {res['status']}"
        )
        
        res = self.request('GET', '/roles/ADMIN/permissions')
        self.log_test(
            "Get ADMIN permissions",
            res['success'] and 'permissions' in res['data'],
            f"Permissions: {res['data'].get('permissions', [])}"
        )
        
        res = self.request('GET', '/roles/CASHIER/permissions')
        self.log_test(
            "Get CASHIER permissions",
            res['success'] and 'create_order' in res['data'].get('permissions', []),
            f"Permissions: {res['data'].get('permissions', [])}"
        )
        
        res = self.request('GET', '/roles/ADMIN/check/all')
        self.log_test(
            "ADMIN has 'all' permission",
            res['success'] and res['data'].get('has_permission') == True,
            f"Has permission: {res['data'].get('has_permission')}"
        )
        
        res = self.request('GET', '/roles/CASHIER/check/create_order')
        self.log_test(
            "CASHIER has 'create_order' permission",
            res['success'] and res['data'].get('has_permission') == True,
            f"Has permission: {res['data'].get('has_permission')}"
        )
        
        res = self.request('GET', '/roles/USER/check/manage_users')
        self.log_test(
            "USER doesn't have 'manage_users' permission",
            res['success'] and res['data'].get('has_permission') == False,
            f"Has permission: {res['data'].get('has_permission')}"
        )
        
        res = self.request('GET', '/roles/stats')
        self.log_test(
            "Get role stats",
            res['success'] and 'stats' in res['data'],
            f"Total: {res['data'].get('total', 0)}"
        )
        
        res = self.request('GET', '/roles/ADMIN/manageable')
        self.log_test(
            "Get manageable roles for ADMIN",
            res['success'] and 'manageable_roles' in res['data'],
            f"Can manage: {len(res['data'].get('manageable_roles', []))} roles"
        )
        
        res = self.request('GET', '/roles/CASHIER/manageable')
        self.log_test(
            "Get manageable roles for CASHIER",
            res['success'],
            f"Can manage: {len(res['data'].get('manageable_roles', []))} roles"
        )
        
        res = self.request('GET', '/roles/validate', params={'role': 'ADMIN'})
        self.log_test(
            "Validate ADMIN role",
            res['success'] and res['data'].get('is_valid') == True,
            f"Is valid: {res['data'].get('is_valid')}"
        )
        
        res = self.request('GET', '/roles/validate', params={'role': 'FAKE_ROLE'})
        self.log_test(
            "Validate invalid role",
            res['success'] and res['data'].get('is_valid') == False,
            f"Is valid: {res['data'].get('is_valid')}"
        )
    
    def cleanup(self):
        self.log("\n🧹 CLEANUP", Colors.YELLOW)
        self.log("-" * 40)
        
        for user_id in self.created_users:
            self.request('DELETE', f'/users/{user_id}/delete', params={'hard': 'true'})
        self.log(f"  Cleaned up {len(self.created_users)} test users", Colors.YELLOW)
        
        for cat_id in self.created_categories:
            self.request('DELETE', f'/categories/{cat_id}/delete', params={'hard': 'true'})
        self.log(f"  Cleaned up {len(self.created_categories)} test categories", Colors.YELLOW)
    
    def print_summary(self):
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        self.log(f"\n{'='*60}", Colors.BOLD)
        self.log("  TEST SUMMARY", Colors.BOLD)
        self.log(f"{'='*60}", Colors.BOLD)
        self.log(f"  Total Tests: {total}")
        self.log(f"  Passed: {self.passed}", Colors.GREEN)
        self.log(f"  Failed: {self.failed}", Colors.RED if self.failed > 0 else Colors.GREEN)
        self.log(f"  Pass Rate: {pass_rate:.1f}%", Colors.GREEN if pass_rate >= 80 else Colors.YELLOW)
        self.log(f"{'='*60}\n", Colors.BOLD)
        
        if self.failed > 0:
            self.log("  FAILED TESTS:", Colors.RED)
            for result in self.results:
                if not result['passed']:
                    self.log(f"    - {result['name']}: {result['message']}", Colors.RED)
            print()


if __name__ == '__main__':
    import sys
    
    base_url = sys.argv[1] if len(sys.argv) > 1 else BASE_URL
    
    runner = TestRunner(base_url)
    runner.run_all()