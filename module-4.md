# Adding metrics collection

In this exercise, we'll add metrics collection to the agent.

Step 1: Add the import to the `agent.py` file:

    ```python
    from livekit.agents import metrics, MetricsCollectedEvent
    ```

Step 2: Add the metrics collection to the `entrypoint` function, before the `session.start` call:

    ```python
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    # At shutdown, generate and log the summary from the usage collector
    ctx.add_shutdown_callback(log_usage)
    ```

Now you should see real merics appear in the console when you run the agent.

# Pre-emptive generation

Add the pre-emptive generation to the `AgentSession` constructor:

    ```python
    preemptive_generation=True,
    ```
    