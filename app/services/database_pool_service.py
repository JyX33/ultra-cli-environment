# ABOUTME: Advanced database connection pool management with performance monitoring and optimization
# ABOUTME: Provides pool health checks, metrics collection, and dynamic pool configuration

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
import threading
import time
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import Pool, QueuePool, StaticPool

from app.core.config import Config
from app.core.structured_logging import get_logger
from app.services.performance_monitoring_service import PerformanceMonitoringService

# Set up structured logging
logger = get_logger(__name__)


@dataclass
class PoolMetrics:
    """Detailed connection pool metrics for monitoring and analysis."""
    pool_size: int = 0
    checked_in: int = 0
    checked_out: int = 0
    overflow: int = 0
    invalid: int = 0
    total_checkouts: int = 0
    total_checkins: int = 0
    total_connects: int = 0
    total_disconnects: int = 0
    checkout_failures: int = 0
    connection_errors: int = 0
    pool_timeouts: int = 0
    avg_checkout_time_ms: float = 0.0
    max_checkout_time_ms: float = 0.0
    pool_utilization_percent: float = 0.0
    overflow_utilization_percent: float = 0.0
    checkout_queue_length: int = 0
    last_reset: datetime = field(default_factory=datetime.now)


@dataclass
class PoolHealthStatus:
    """Pool health assessment and recommendations."""
    status: str  # healthy, warning, critical
    utilization_score: float  # 0-100
    performance_score: float  # 0-100
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    needs_intervention: bool = False


@dataclass
class PoolConfiguration:
    """Advanced connection pool configuration options."""
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: float = 30.0
    pool_recycle: int = 300
    pool_pre_ping: bool = True
    pool_reset_on_return: str = "commit"  # commit, rollback, None
    pool_invalid_on_exception: bool = True
    pool_heartbeat_interval: int = 30
    connect_timeout: float = 10.0
    query_timeout: float = 60.0
    enable_monitoring: bool = True
    pool_size_max_threshold: float = 0.8
    pool_checkout_timeout: float = 10.0
    overflow_ratio_warning: float = 0.7

    @classmethod
    def from_config(cls) -> 'PoolConfiguration':
        """Create pool configuration from application config."""
        return cls(
            pool_size=Config.DATABASE_POOL_SIZE,
            max_overflow=Config.DATABASE_MAX_OVERFLOW,
            pool_timeout=Config.DATABASE_POOL_TIMEOUT,
            pool_recycle=Config.DATABASE_POOL_RECYCLE,
            pool_pre_ping=Config.DATABASE_POOL_PRE_PING,
            pool_reset_on_return=Config.DATABASE_POOL_RESET_ON_RETURN,
            pool_invalid_on_exception=Config.DATABASE_POOL_INVALID_ON_EXCEPTION,
            pool_heartbeat_interval=Config.DATABASE_POOL_HEARTBEAT_INTERVAL,
            connect_timeout=Config.DATABASE_CONNECT_TIMEOUT,
            query_timeout=Config.DATABASE_QUERY_TIMEOUT,
            enable_monitoring=Config.DATABASE_ENABLE_POOL_MONITORING,
            pool_size_max_threshold=Config.DATABASE_POOL_SIZE_MAX_THRESHOLD,
            pool_checkout_timeout=Config.DATABASE_POOL_CHECKOUT_TIMEOUT,
            overflow_ratio_warning=Config.DATABASE_POOL_OVERFLOW_RATIO_WARNING
        )


class DatabasePoolService:
    """Advanced database connection pool management service with comprehensive monitoring."""

    def __init__(
        self,
        database_url: str,
        config: PoolConfiguration | None = None,
        performance_monitor: PerformanceMonitoringService | None = None
    ):
        """Initialize database pool service with enhanced configuration.

        Args:
            database_url: Database connection URL
            config: Pool configuration options
            performance_monitor: Optional performance monitoring service
        """
        self.database_url = database_url
        self.config = config or PoolConfiguration.from_config()
        self.performance_monitor = performance_monitor

        # Pool monitoring state
        self._metrics = PoolMetrics()
        self._monitoring_active = False
        self._monitoring_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Checkout timing tracking
        self._checkout_times: dict[int, float] = {}
        self._checkout_queue_length = 0

        # Initialize engine and session factory
        self.engine = self._create_optimized_engine()
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

        # Set up event listeners for monitoring
        if self.config.enable_monitoring:
            self._setup_pool_monitoring()

        logger.info(
            f"Initialized database pool service with pool_size={self.config.pool_size}, "
            f"max_overflow={self.config.max_overflow}, monitoring={'enabled' if self.config.enable_monitoring else 'disabled'}"
        )

    def _create_optimized_engine(self) -> Engine:
        """Create SQLAlchemy engine with optimized pool configuration."""
        try:
            parsed_url = urlparse(self.database_url)
            engine_kwargs = {
                "echo": False,  # Disable SQL echo for production
                "pool_pre_ping": self.config.pool_pre_ping,
                "pool_recycle": self.config.pool_recycle,
            }

            if parsed_url.scheme == "sqlite":
                # SQLite configuration with optimizations
                engine_kwargs.update({
                    "poolclass": StaticPool,
                    "connect_args": {
                        "check_same_thread": False,
                        "timeout": self.config.connect_timeout,
                        "isolation_level": None  # Enable autocommit mode for better performance
                    }
                })
            elif parsed_url.scheme.startswith("postgresql"):
                # PostgreSQL configuration with advanced pooling
                engine_kwargs.update({
                    "poolclass": QueuePool,
                    "pool_size": self.config.pool_size,
                    "max_overflow": self.config.max_overflow,
                    "pool_timeout": self.config.pool_timeout,
                    "pool_reset_on_return": self.config.pool_reset_on_return,
                    "connect_args": {
                        "connect_timeout": int(self.config.connect_timeout),
                        "command_timeout": int(self.config.query_timeout),
                        "server_settings": {
                            "jit": "off",  # Disable JIT for consistent performance
                            "application_name": "ai_reddit_agent"
                        }
                    }
                })

            engine = create_engine(self.database_url, **engine_kwargs)

            # Validate connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            logger.info("Database engine created and validated successfully")
            return engine

        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise SQLAlchemyError(f"Database engine creation failed: {e}") from e

    def _setup_pool_monitoring(self) -> None:
        """Set up SQLAlchemy event listeners for comprehensive pool monitoring."""

        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_connection, connection_record):
            """Track new connections."""
            with self._lock:
                self._metrics.total_connects += 1

        @event.listens_for(self.engine, "close")
        def receive_close(dbapi_connection, connection_record):
            """Track connection closures."""
            with self._lock:
                self._metrics.total_disconnects += 1

        @event.listens_for(Pool, "checkout")
        def receive_checkout(dbapi_connection, connection_record, connection_proxy):
            """Track connection checkouts with timing."""
            connection_id = id(connection_proxy)
            checkout_time = time.perf_counter()

            with self._lock:
                self._metrics.total_checkouts += 1
                self._checkout_times[connection_id] = checkout_time

        @event.listens_for(Pool, "checkin")
        def receive_checkin(dbapi_connection, connection_record):
            """Track connection checkins and calculate checkout duration."""
            checkin_time = time.perf_counter()

            with self._lock:
                self._metrics.total_checkins += 1

                # Calculate checkout duration if we have the checkout time
                connection_id = id(connection_record)
                if connection_id in self._checkout_times:
                    checkout_duration = (checkin_time - self._checkout_times[connection_id]) * 1000

                    # Update checkout time statistics
                    if self._metrics.total_checkouts > 0:
                        self._metrics.avg_checkout_time_ms = (
                            (self._metrics.avg_checkout_time_ms * (self._metrics.total_checkouts - 1) + checkout_duration)
                            / self._metrics.total_checkouts
                        )
                    self._metrics.max_checkout_time_ms = max(self._metrics.max_checkout_time_ms, checkout_duration)

                    del self._checkout_times[connection_id]

        @event.listens_for(Pool, "invalidate")
        def receive_invalidate(dbapi_connection, connection_record, exception):
            """Track connection invalidations."""
            with self._lock:
                self._metrics.invalid += 1
                if exception:
                    self._metrics.connection_errors += 1

            logger.warning(f"Database connection invalidated: {exception}")

    def start_monitoring(self) -> None:
        """Start background pool monitoring thread."""
        if self._monitoring_active or not self.config.enable_monitoring:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()

        logger.info("Database pool monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background pool monitoring."""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5.0)

        logger.info("Database pool monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop for pool metrics collection."""
        while self._monitoring_active:
            try:
                self._update_pool_metrics()
                self._check_pool_health()

                if self.performance_monitor:
                    self._record_performance_metrics()

                time.sleep(self.config.pool_heartbeat_interval)

            except Exception as e:
                logger.error(f"Error in pool monitoring loop: {e}")
                time.sleep(self.config.pool_heartbeat_interval)

    def _update_pool_metrics(self) -> None:
        """Update current pool metrics from the engine pool."""
        if not hasattr(self.engine.pool, 'size'):
            return

        try:
            pool = self.engine.pool

            with self._lock:
                self._metrics.pool_size = pool.size()
                self._metrics.checked_in = getattr(pool, 'checkedin', lambda: 0)()
                self._metrics.checked_out = getattr(pool, 'checkedout', lambda: 0)()
                self._metrics.overflow = getattr(pool, 'overflow', lambda: 0)()

                # Calculate utilization percentages
                if self._metrics.pool_size > 0:
                    self._metrics.pool_utilization_percent = (
                        self._metrics.checked_out / self._metrics.pool_size * 100
                    )

                if self.config.max_overflow > 0:
                    self._metrics.overflow_utilization_percent = (
                        self._metrics.overflow / self.config.max_overflow * 100
                    )

        except Exception as e:
            logger.warning(f"Failed to update pool metrics: {e}")

    def _check_pool_health(self) -> None:
        """Check pool health and generate alerts if needed."""
        health_status = self.assess_pool_health()

        if health_status.needs_intervention:
            logger.warning(
                f"Pool health issue detected: {health_status.status}. "
                f"Warnings: {', '.join(health_status.warnings)}"
            )

            if self.performance_monitor:
                for warning in health_status.warnings:
                    self.performance_monitor.record_metric(
                        "database_pool_warning",
                        1,
                        "count",
                        {"warning": warning, "status": health_status.status}
                    )

    def _record_performance_metrics(self) -> None:
        """Record pool metrics in performance monitoring service."""
        if not self.performance_monitor:
            return

        metrics_to_record = {
            "pool_utilization_percent": self._metrics.pool_utilization_percent,
            "pool_checkout_time_avg_ms": self._metrics.avg_checkout_time_ms,
            "pool_checkout_failures": self._metrics.checkout_failures,
            "pool_connection_errors": self._metrics.connection_errors,
            "pool_overflow_utilization": self._metrics.overflow_utilization_percent
        }

        for metric_name, value in metrics_to_record.items():
            self.performance_monitor.record_metric(
                f"database_{metric_name}",
                value,
                "gauge",
                {"service": "database_pool"}
            )

    def get_pool_metrics(self) -> PoolMetrics:
        """Get current pool metrics snapshot."""
        with self._lock:
            # Update real-time metrics
            self._update_pool_metrics()
            return PoolMetrics(**asdict(self._metrics))

    def assess_pool_health(self) -> PoolHealthStatus:
        """Assess current pool health and provide recommendations."""
        metrics = self.get_pool_metrics()
        status = PoolHealthStatus(status="healthy", utilization_score=100, performance_score=100)

        # Check pool utilization
        if metrics.pool_utilization_percent > self.config.pool_size_max_threshold * 100:
            status.warnings.append(f"High pool utilization: {metrics.pool_utilization_percent:.1f}%")
            status.utilization_score -= 30
            status.needs_intervention = True

        # Check overflow utilization
        if metrics.overflow_utilization_percent > self.config.overflow_ratio_warning * 100:
            status.warnings.append(f"High overflow utilization: {metrics.overflow_utilization_percent:.1f}%")
            status.utilization_score -= 20
            status.needs_intervention = True

        # Check checkout performance
        if metrics.avg_checkout_time_ms > 100:  # More than 100ms average
            status.warnings.append(f"Slow connection checkout: {metrics.avg_checkout_time_ms:.1f}ms avg")
            status.performance_score -= 25

        # Check error rates
        total_operations = metrics.total_checkouts + metrics.total_checkins
        if total_operations > 0:
            error_rate = (metrics.checkout_failures + metrics.connection_errors) / total_operations
            if error_rate > 0.05:  # More than 5% error rate
                status.warnings.append(f"High error rate: {error_rate:.2%}")
                status.performance_score -= 40
                status.needs_intervention = True

        # Generate recommendations
        if metrics.pool_utilization_percent > 80:
            status.recommendations.append("Consider increasing pool_size")

        if metrics.overflow_utilization_percent > 70:
            status.recommendations.append("Consider increasing max_overflow")

        if metrics.avg_checkout_time_ms > 50:
            status.recommendations.append("Investigate connection checkout performance")

        # Determine overall status
        overall_score = (status.utilization_score + status.performance_score) / 2
        if overall_score < 60:
            status.status = "critical"
        elif overall_score < 80:
            status.status = "warning"

        return status

    def reset_pool_metrics(self) -> None:
        """Reset pool metrics counters."""
        with self._lock:
            self._metrics = PoolMetrics()
            self._checkout_times.clear()

        logger.info("Pool metrics reset")

    def optimize_pool_settings(self) -> dict[str, Any]:
        """Provide pool optimization recommendations based on current metrics."""
        metrics = self.get_pool_metrics()
        recommendations = {}

        # Analyze utilization patterns
        if metrics.pool_utilization_percent > 85:
            recommended_pool_size = int(self.config.pool_size * 1.3)
            recommendations["pool_size"] = min(recommended_pool_size, 50)  # Cap at 50

        if metrics.overflow_utilization_percent > 75:
            recommended_overflow = int(self.config.max_overflow * 1.2)
            recommendations["max_overflow"] = min(recommended_overflow, 100)  # Cap at 100

        # Analyze performance patterns
        if metrics.avg_checkout_time_ms > 100:
            recommendations["pool_pre_ping"] = False  # Disable if causing delays
            recommendations["pool_timeout"] = min(self.config.pool_timeout * 0.8, 20)

        return recommendations

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        """Get database session with enhanced error handling and monitoring."""
        session = None
        checkout_start = time.perf_counter()

        try:
            session = self.SessionLocal()
            checkout_duration = (time.perf_counter() - checkout_start) * 1000

            # Record successful checkout
            if self.performance_monitor:
                self.performance_monitor.record_metric(
                    "database_session_checkout_time",
                    checkout_duration,
                    "ms",
                    {"status": "success"}
                )

            yield session

        except SQLTimeoutError as e:
            with self._lock:
                self._metrics.pool_timeouts += 1
                self._metrics.checkout_failures += 1

            logger.error(f"Database pool timeout: {e}")

            if self.performance_monitor:
                self.performance_monitor.record_metric(
                    "database_pool_timeout",
                    1,
                    "count",
                    {"error": "timeout"}
                )
            raise

        except SQLAlchemyError as e:
            with self._lock:
                self._metrics.connection_errors += 1
                self._metrics.checkout_failures += 1

            logger.error(f"Database connection error: {e}")

            if self.performance_monitor:
                self.performance_monitor.record_metric(
                    "database_connection_error",
                    1,
                    "count",
                    {"error": str(type(e).__name__)}
                )
            raise

        finally:
            if session:
                try:
                    session.close()
                except Exception as e:
                    logger.warning(f"Error closing database session: {e}")

    def get_pool_status_report(self) -> dict[str, Any]:
        """Generate comprehensive pool status report."""
        metrics = self.get_pool_metrics()
        health = self.assess_pool_health()
        optimization_recommendations = self.optimize_pool_settings()

        return {
            "pool_configuration": asdict(self.config),
            "current_metrics": asdict(metrics),
            "health_status": asdict(health),
            "optimization_recommendations": optimization_recommendations,
            "monitoring_active": self._monitoring_active,
            "generated_at": datetime.now().isoformat()
        }

    def __enter__(self) -> 'DatabasePoolService':
        """Context manager entry."""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.stop_monitoring()
        if hasattr(self, 'engine'):
            self.engine.dispose()


# Global pool service instance
_pool_service: DatabasePoolService | None = None


def get_database_pool_service(
    database_url: str | None = None,
    performance_monitor: PerformanceMonitoringService | None = None
) -> DatabasePoolService:
    """Get or create the global database pool service.

    Args:
        database_url: Database URL (uses config default if None)
        performance_monitor: Optional performance monitoring service

    Returns:
        DatabasePoolService instance
    """
    global _pool_service

    if _pool_service is None:
        from app.db.session import get_database_url
        url = database_url or get_database_url()
        _pool_service = DatabasePoolService(url, performance_monitor=performance_monitor)
        logger.info("Created global database pool service")

    return _pool_service


def cleanup_database_pool_service() -> None:
    """Clean up the global database pool service."""
    global _pool_service

    if _pool_service is not None:
        _pool_service.stop_monitoring()
        if hasattr(_pool_service, 'engine'):
            _pool_service.engine.dispose()
        _pool_service = None
        logger.info("Cleaned up global database pool service")

