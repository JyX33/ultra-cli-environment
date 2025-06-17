# ABOUTME: Database maintenance utilities for scheduled cleanup and optimization tasks
# ABOUTME: Provides scheduled operations, database optimization, and maintenance monitoring

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import config
from app.db.session import SessionLocal
from app.services.storage_service import StorageService

# Set up logging
logger = logging.getLogger(__name__)


class DatabaseMaintenanceScheduler:
    """Scheduler for periodic database maintenance operations.

    This class handles scheduled cleanup, archival, and optimization tasks
    to keep the database running efficiently and within storage limits.
    """

    def __init__(self) -> None:
        """Initialize the maintenance scheduler."""
        self.running = False
        self.last_cleanup_time: datetime | None = None
        self.last_optimization_time: datetime | None = None
        self.maintenance_stats: dict[str, Any] = {}

    async def start_scheduler(
        self,
        cleanup_interval_hours: int = 24,
        optimization_interval_hours: int = 168,  # Weekly
    ) -> None:
        """Start the maintenance scheduler.

        Args:
            cleanup_interval_hours: Hours between cleanup operations
            optimization_interval_hours: Hours between database optimization
        """
        if self.running:
            logger.warning("Maintenance scheduler is already running")
            return

        self.running = True
        logger.info(
            f"Starting database maintenance scheduler: "
            f"cleanup every {cleanup_interval_hours}h, "
            f"optimization every {optimization_interval_hours}h"
        )

        try:
            while self.running:
                current_time = datetime.now(UTC)

                # Check if cleanup is needed
                if self._should_run_cleanup(current_time, cleanup_interval_hours):
                    await self._run_cleanup_task()

                # Check if optimization is needed
                if self._should_run_optimization(
                    current_time, optimization_interval_hours
                ):
                    await self._run_optimization_task()

                # Sleep for 1 hour before next check
                await asyncio.sleep(3600)

        except Exception as e:
            logger.error(f"Error in maintenance scheduler: {e}")
            self.running = False
            raise

    def stop_scheduler(self) -> None:
        """Stop the maintenance scheduler."""
        logger.info("Stopping database maintenance scheduler")
        self.running = False

    def _should_run_cleanup(self, current_time: datetime, interval_hours: int) -> bool:
        """Check if cleanup should be run based on interval."""
        if self.last_cleanup_time is None:
            return True

        time_since_last = current_time - self.last_cleanup_time
        return time_since_last >= timedelta(hours=interval_hours)

    def _should_run_optimization(
        self, current_time: datetime, interval_hours: int
    ) -> bool:
        """Check if optimization should be run based on interval."""
        if self.last_optimization_time is None:
            return True

        time_since_last = current_time - self.last_optimization_time
        return time_since_last >= timedelta(hours=interval_hours)

    async def _run_cleanup_task(self) -> None:
        """Run the scheduled cleanup task."""
        logger.info("Starting scheduled cleanup task")
        start_time = time.time()

        try:
            with SessionLocal() as session:
                storage_service = StorageService(session)

                # Get pre-cleanup statistics
                pre_stats = storage_service.get_storage_statistics(
                    include_size_estimation=True,
                    retention_days=config.DATA_RETENTION_DAYS,
                )

                # Perform cleanup or archival based on configuration
                if config.ARCHIVE_OLD_DATA:
                    cleaned_count = storage_service.archive_old_data_from_config()
                    operation_type = "archived"
                else:
                    cleaned_count = storage_service.cleanup_old_data_from_config()
                    operation_type = "deleted"

                # Get post-cleanup statistics
                post_stats = storage_service.get_storage_statistics(
                    include_size_estimation=True
                )

                # Calculate space saved
                pre_size = pre_stats.get("estimated_size", {}).get("total_mb", 0)
                post_size = post_stats.get("estimated_size", {}).get("total_mb", 0)
                space_saved = pre_size - post_size

                duration = time.time() - start_time
                self.last_cleanup_time = datetime.now(UTC)

                # Update maintenance stats
                self.maintenance_stats.update(
                    {
                        "last_cleanup": {
                            "timestamp": self.last_cleanup_time,
                            "operation_type": operation_type,
                            "records_processed": cleaned_count,
                            "space_saved_mb": round(space_saved, 2),
                            "duration_seconds": round(duration, 2),
                            "pre_cleanup_stats": pre_stats,
                            "post_cleanup_stats": post_stats,
                        }
                    }
                )

                logger.info(
                    f"Cleanup task completed: {operation_type} {cleaned_count} records, "
                    f"saved {space_saved:.2f} MB in {duration:.2f} seconds"
                )

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
            self.maintenance_stats["last_cleanup_error"] = {
                "timestamp": datetime.now(UTC),
                "error": str(e),
                "duration_seconds": time.time() - start_time,
            }

    async def _run_optimization_task(self) -> None:
        """Run the scheduled database optimization task."""
        logger.info("Starting scheduled optimization task")
        start_time = time.time()

        try:
            with SessionLocal() as session:
                # Run database-specific optimization commands
                optimization_results = await self._optimize_database(session)

                duration = time.time() - start_time
                self.last_optimization_time = datetime.now(UTC)

                # Update maintenance stats
                self.maintenance_stats.update(
                    {
                        "last_optimization": {
                            "timestamp": self.last_optimization_time,
                            "duration_seconds": round(duration, 2),
                            "operations_performed": optimization_results,
                        }
                    }
                )

                logger.info(
                    f"Optimization task completed in {duration:.2f} seconds: "
                    f"{optimization_results}"
                )

        except Exception as e:
            logger.error(f"Error in optimization task: {e}")
            self.maintenance_stats["last_optimization_error"] = {
                "timestamp": datetime.now(UTC),
                "error": str(e),
                "duration_seconds": time.time() - start_time,
            }

    async def _optimize_database(self, session: Session) -> list[str]:
        """Perform database-specific optimization operations.

        Args:
            session: Database session for executing optimization commands

        Returns:
            List of optimization operations performed
        """
        operations_performed: list[str] = []

        try:
            # Get database type from connection
            if session.bind is None:
                raise RuntimeError("Session has no database connection")

            # Safely get URL attribute
            bind_url = getattr(session.bind, 'url', None)
            if bind_url is None:
                raise RuntimeError("Session bind has no URL attribute")
            db_url = str(bind_url)

            if "sqlite" in db_url.lower():
                # SQLite-specific optimizations
                await self._optimize_sqlite(session, operations_performed)
            elif "postgresql" in db_url.lower():
                # PostgreSQL-specific optimizations
                await self._optimize_postgresql(session, operations_performed)
            else:
                logger.warning(f"Unknown database type for optimization: {db_url}")

        except Exception as e:
            logger.error(f"Error during database optimization: {e}")
            operations_performed.append(f"Error: {e}")

        return operations_performed

    async def _optimize_sqlite(self, session: Session, operations: list[str]) -> None:
        """Perform SQLite-specific optimizations."""
        try:
            # VACUUM to reclaim space and defragment
            session.execute(text("VACUUM"))
            operations.append("VACUUM executed")

            # ANALYZE to update query planner statistics
            session.execute(text("ANALYZE"))
            operations.append("ANALYZE executed")

            # Check integrity
            integrity_result = session.execute(
                text("PRAGMA integrity_check")
            ).fetchone()
            if integrity_result and integrity_result[0] == "ok":
                operations.append("Integrity check passed")
            else:
                operations.append(f"Integrity check warning: {integrity_result}")

            session.commit()

        except SQLAlchemyError as e:
            logger.error(f"SQLite optimization error: {e}")
            session.rollback()
            operations.append(f"SQLite optimization error: {e}")

    async def _optimize_postgresql(
        self, session: Session, operations: list[str]
    ) -> None:
        """Perform PostgreSQL-specific optimizations."""
        try:
            # VACUUM ANALYZE to reclaim space and update statistics
            session.execute(text("VACUUM ANALYZE"))
            operations.append("VACUUM ANALYZE executed")

            # Update table statistics
            session.execute(text("ANALYZE"))
            operations.append("ANALYZE executed")

            session.commit()

        except SQLAlchemyError as e:
            logger.error(f"PostgreSQL optimization error: {e}")
            session.rollback()
            operations.append(f"PostgreSQL optimization error: {e}")

    def get_maintenance_status(self) -> dict[str, Any]:
        """Get current maintenance status and statistics.

        Returns:
            Dictionary containing maintenance status and recent operation results
        """
        status: dict[str, Any] = {
            "scheduler_running": self.running,
            "last_cleanup_time": self.last_cleanup_time,
            "last_optimization_time": self.last_optimization_time,
            "maintenance_stats": self.maintenance_stats,
            "configuration": {
                "data_retention_days": config.DATA_RETENTION_DAYS,
                "archive_enabled": config.ARCHIVE_OLD_DATA,
                "cleanup_batch_size": config.CLEANUP_BATCH_SIZE,
            },
        }

        # Add health indicators
        current_time = datetime.now(UTC)
        if self.last_cleanup_time:
            hours_since_cleanup = (
                current_time - self.last_cleanup_time
            ).total_seconds() / 3600
            status["hours_since_last_cleanup"] = float(round(hours_since_cleanup, 1))

        if self.last_optimization_time:
            hours_since_optimization = (
                current_time - self.last_optimization_time
            ).total_seconds() / 3600
            status["hours_since_last_optimization"] = float(round(hours_since_optimization, 1))

        return status


class MaintenanceOperations:
    """Manual maintenance operations for immediate execution.

    This class provides methods for running maintenance operations
    on demand, outside of the scheduled context.
    """

    @staticmethod
    def run_immediate_cleanup(
        days_to_keep: int | None = None,
        archive_mode: bool | None = None,
    ) -> dict[str, Any]:
        """Run immediate cleanup operation.

        Args:
            days_to_keep: Override default retention days
            archive_mode: Override default archive setting

        Returns:
            Dictionary with cleanup results and statistics
        """
        start_time = time.time()
        logger.info("Starting immediate cleanup operation")

        try:
            with SessionLocal() as session:
                storage_service = StorageService(session)

                # Use provided parameters or fall back to config
                retention_days = days_to_keep or config.DATA_RETENTION_DAYS
                use_archive = (
                    archive_mode
                    if archive_mode is not None
                    else config.ARCHIVE_OLD_DATA
                )

                # Get pre-cleanup statistics
                pre_stats = storage_service.get_storage_statistics(
                    include_size_estimation=True,
                    retention_days=retention_days,
                )

                # Perform cleanup or archival
                if use_archive:
                    cleaned_count = storage_service.archive_old_check_runs(
                        days_to_keep=retention_days,
                        batch_size=config.CLEANUP_BATCH_SIZE,
                    )
                    operation_type = "archived"
                else:
                    cleaned_count = storage_service.cleanup_old_data(
                        days_to_keep=retention_days,
                        batch_size=config.CLEANUP_BATCH_SIZE,
                    )
                    operation_type = "deleted"

                # Get post-cleanup statistics
                post_stats = storage_service.get_storage_statistics(
                    include_size_estimation=True
                )

                # Calculate metrics
                pre_size = pre_stats.get("estimated_size", {}).get("total_mb", 0)
                post_size = post_stats.get("estimated_size", {}).get("total_mb", 0)
                space_saved = pre_size - post_size
                duration = time.time() - start_time

                result = {
                    "success": True,
                    "operation_type": operation_type,
                    "records_processed": cleaned_count,
                    "space_saved_mb": round(space_saved, 2),
                    "duration_seconds": round(duration, 2),
                    "retention_days": retention_days,
                    "timestamp": datetime.now(UTC),
                    "pre_cleanup_stats": pre_stats,
                    "post_cleanup_stats": post_stats,
                }

                logger.info(
                    f"Immediate cleanup completed: {operation_type} {cleaned_count} records, "
                    f"saved {space_saved:.2f} MB in {duration:.2f} seconds"
                )

                return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error in immediate cleanup: {e}")

            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(duration, 2),
                "timestamp": datetime.now(UTC),
            }

    @staticmethod
    def run_immediate_optimization() -> dict[str, Any]:
        """Run immediate database optimization.

        Returns:
            Dictionary with optimization results
        """
        start_time = time.time()
        logger.info("Starting immediate optimization operation")

        try:
            with SessionLocal() as session:
                # Create a temporary scheduler instance for the optimization logic
                temp_scheduler = DatabaseMaintenanceScheduler()

                # Run optimization synchronously by calling the async method in sync context
                import asyncio

                try:
                    # Try to get the current event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're in an async context, we need to handle this differently
                        # For now, fall back to basic optimization
                        operations_performed = []

                        # Get database type and run basic optimization
                        if session.bind is None:
                            raise RuntimeError("Session has no database connection")

                        # Safely get URL attribute
                        bind_url = getattr(session.bind, 'url', None)
                        if bind_url is None:
                            raise RuntimeError("Session bind has no URL attribute")
                        db_url = str(bind_url)
                        if "sqlite" in db_url.lower():
                            session.execute(text("VACUUM"))
                            session.execute(text("ANALYZE"))
                            operations_performed = [
                                "VACUUM executed",
                                "ANALYZE executed",
                            ]
                        elif "postgresql" in db_url.lower():
                            session.execute(text("VACUUM ANALYZE"))
                            operations_performed = ["VACUUM ANALYZE executed"]

                        session.commit()
                    else:
                        # We can run the async method
                        operations_performed = loop.run_until_complete(
                            temp_scheduler._optimize_database(session)
                        )
                except RuntimeError:
                    # No event loop, create one
                    operations_performed = asyncio.run(
                        temp_scheduler._optimize_database(session)
                    )

                duration = time.time() - start_time

                result = {
                    "success": True,
                    "operations_performed": operations_performed,
                    "duration_seconds": round(duration, 2),
                    "timestamp": datetime.now(UTC),
                }

                logger.info(
                    f"Immediate optimization completed in {duration:.2f} seconds: "
                    f"{operations_performed}"
                )

                return result

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error in immediate optimization: {e}")

            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(duration, 2),
                "timestamp": datetime.now(UTC),
            }

    @staticmethod
    def get_maintenance_recommendations() -> dict[str, Any]:
        """Get maintenance recommendations based on current database state.

        Returns:
            Dictionary with maintenance recommendations and current status
        """
        try:
            with SessionLocal() as session:
                storage_service = StorageService(session)

                # Get comprehensive statistics
                stats = storage_service.get_storage_statistics(
                    include_date_breakdown=True,
                    include_size_estimation=True,
                    retention_days=config.DATA_RETENTION_DAYS,
                )

                # Generate recommendations
                recommendations = []
                urgency_level = "low"

                # Check data age
                if "retention_analysis" in stats:
                    cleanup_count = stats["retention_analysis"]["data_to_cleanup"]
                    cleanup_percentage = stats["retention_analysis"][
                        "cleanup_percentage"
                    ]

                    if cleanup_count > 0:
                        if cleanup_percentage > 50:
                            urgency_level = "high"
                            recommendations.append(
                                f"HIGH PRIORITY: {cleanup_count} old check runs ({cleanup_percentage}%) "
                                "should be cleaned up immediately"
                            )
                        elif cleanup_percentage > 25:
                            urgency_level = "medium"
                            recommendations.append(
                                f"MEDIUM PRIORITY: {cleanup_count} old check runs ({cleanup_percentage}%) "
                                "should be cleaned up soon"
                            )
                        else:
                            recommendations.append(
                                f"Consider cleaning up {cleanup_count} old check runs ({cleanup_percentage}%)"
                            )

                # Check database size
                total_mb = stats.get("estimated_size", {}).get("total_mb", 0)
                if total_mb > 500:
                    urgency_level = max(urgency_level, "high")
                    recommendations.append(
                        f"HIGH PRIORITY: Database size is {total_mb} MB, consider immediate cleanup"
                    )
                elif total_mb > 100:
                    urgency_level = max(urgency_level, "medium")
                    recommendations.append(
                        f"Database size is {total_mb} MB, consider enabling archival"
                    )

                # Check data span
                if "date_breakdown" in stats:
                    data_span = stats["date_breakdown"]["data_span_days"]
                    if data_span > config.DATA_RETENTION_DAYS * 2:
                        recommendations.append(
                            f"Data spans {data_span} days, much longer than retention period of "
                            f"{config.DATA_RETENTION_DAYS} days"
                        )

                # Default recommendation if no issues
                if not recommendations:
                    recommendations.append(
                        "Database is in good condition, no immediate action needed"
                    )

                return {
                    "urgency_level": urgency_level,
                    "recommendations": recommendations,
                    "current_stats": stats,
                    "configuration": {
                        "retention_days": config.DATA_RETENTION_DAYS,
                        "archive_enabled": config.ARCHIVE_OLD_DATA,
                        "batch_size": config.CLEANUP_BATCH_SIZE,
                    },
                    "timestamp": datetime.now(UTC),
                }

        except Exception as e:
            logger.error(f"Error generating maintenance recommendations: {e}")
            return {
                "urgency_level": "unknown",
                "recommendations": [f"Error generating recommendations: {e}"],
                "error": str(e),
                "timestamp": datetime.now(UTC),
            }


# Global maintenance scheduler instance
maintenance_scheduler = DatabaseMaintenanceScheduler()


def create_maintenance_task() -> Callable[[], Any]:
    """Create a maintenance task function for use with task schedulers.

    Returns:
        Function that can be called to run maintenance operations
    """

    def maintenance_task() -> dict[str, Any]:
        """Run maintenance operations synchronously."""
        return MaintenanceOperations.run_immediate_cleanup()

    return maintenance_task
