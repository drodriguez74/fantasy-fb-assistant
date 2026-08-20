"""
Comprehensive error handling utilities for external API integrations
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Callable, TypeVar, List
from functools import wraps
import httpx
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar('T')


class APIError(Exception):
    """Base exception for API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, service: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.service = service
        super().__init__(self.message)


class RateLimitError(APIError):
    """Exception for rate limiting errors"""
    def __init__(self, service: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = f"Rate limit exceeded for {service}"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message, 429, service)


class ServiceUnavailableError(APIError):
    """Exception for service unavailability"""
    pass


class AuthenticationError(APIError):
    """Exception for authentication failures"""
    pass


def with_retry(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    retry_on: List[Exception] = None
):
    """Decorator for retrying failed API calls"""
    if retry_on is None:
        retry_on = [httpx.RequestError, httpx.TimeoutException, ServiceUnavailableError]
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if this exception should be retried
                    should_retry = any(isinstance(e, retry_type) for retry_type in retry_on)
                    
                    if not should_retry or attempt == max_retries:
                        break
                    
                    # Calculate backoff delay
                    delay = backoff_factor * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {str(e)}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
            
            # If we get here, all retries failed
            logger.error(f"All {max_retries + 1} attempts failed for {func.__name__}: {str(last_exception)}")
            raise last_exception
        
        return wrapper
    return decorator


def handle_http_errors(response: httpx.Response, service_name: str) -> None:
    """Handle common HTTP errors from external APIs"""
    if response.status_code == 200:
        return
    
    try:
        error_data = response.json()
        error_message = error_data.get('message', error_data.get('error', 'Unknown error'))
    except:
        error_message = response.text or f"HTTP {response.status_code} error"
    
    if response.status_code == 401:
        raise AuthenticationError(f"{service_name} authentication failed: {error_message}", 401, service_name)
    elif response.status_code == 403:
        raise AuthenticationError(f"{service_name} access forbidden: {error_message}", 403, service_name)
    elif response.status_code == 429:
        retry_after = response.headers.get('Retry-After')
        retry_seconds = int(retry_after) if retry_after else None
        raise RateLimitError(service_name, retry_seconds)
    elif response.status_code >= 500:
        raise ServiceUnavailableError(f"{service_name} service unavailable: {error_message}", response.status_code, service_name)
    else:
        raise APIError(f"{service_name} error: {error_message}", response.status_code, service_name)


class CircuitBreaker:
    """Circuit breaker pattern for external API calls"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable[..., T]) -> Callable[..., T]:
        """Wrap a function with circuit breaker logic"""
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise ServiceUnavailableError(f"Circuit breaker OPEN for {func.__name__}")
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        return datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def _on_success(self):
        """Reset circuit breaker on successful call"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """Handle failure and potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")


def safe_api_call(
    service_name: str,
    default_response: Any = None,
    log_errors: bool = True
):
    """Decorator for safe API calls with fallback responses"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except AuthenticationError as e:
                if log_errors:
                    logger.error(f"{service_name} authentication error: {str(e)}")
                if default_response is not None:
                    return default_response
                raise HTTPException(status_code=401, detail=f"{service_name} authentication failed")
            except RateLimitError as e:
                if log_errors:
                    logger.warning(f"{service_name} rate limit hit: {str(e)}")
                if default_response is not None:
                    return default_response
                raise HTTPException(status_code=429, detail=f"{service_name} rate limit exceeded")
            except ServiceUnavailableError as e:
                if log_errors:
                    logger.error(f"{service_name} service unavailable: {str(e)}")
                if default_response is not None:
                    return default_response
                raise HTTPException(status_code=503, detail=f"{service_name} temporarily unavailable")
            except APIError as e:
                if log_errors:
                    logger.error(f"{service_name} API error: {str(e)}")
                if default_response is not None:
                    return default_response
                raise HTTPException(status_code=e.status_code or 500, detail=str(e))
            except Exception as e:
                if log_errors:
                    logger.error(f"Unexpected error in {service_name}: {str(e)}")
                if default_response is not None:
                    return default_response
                raise HTTPException(status_code=500, detail=f"Internal error with {service_name}")
        
        return wrapper
    return decorator


async def validate_api_response(response: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """Validate API response contains required fields"""
    missing_fields = [field for field in required_fields if field not in response]
    
    if missing_fields:
        raise APIError(f"API response missing required fields: {', '.join(missing_fields)}")
    
    return response


def create_fallback_response(service_name: str, operation: str) -> Dict[str, Any]:
    """Create a standard fallback response for failed API calls"""
    return {
        "error": f"{service_name} temporarily unavailable",
        "service": service_name,
        "operation": operation,
        "timestamp": datetime.utcnow().isoformat(),
        "fallback": True
    }


# Global circuit breakers for each service
sleeper_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
espn_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
yahoo_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)