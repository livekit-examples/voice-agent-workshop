# Adding metrics collection

In this exercise, we'll add metrics collection to the agent. This includes stats on each components, as well as a custom stat measuring the total time for the agent to respond in audio.

Step 1: Add the import to the `agent.py` file:

    ```python
    from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent
    ```

Step 2: Add the metrics collection to the `entrypoint` function, before the `session.start` call:

    ```python
    usage_collector = metrics.UsageCollector()
    last_eou_metrics: metrics.EOUMetrics | None = None

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        nonlocal last_eou_metrics
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics
        
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        if (
            ev.new_state == "speaking"
            and last_eou_metrics
            and last_eou_metrics.speech_id == session.current_speech.id
        ):
            logger.info(
                f"Agent response - Time to first audio frame: {ev.created_at - last_eou_metrics.last_speaking_time}"
            )
    ```

Now you should see real merics appear in the console when you run the agent.

# Pre-emptive generation

Now we'll turn on a feature to speed up handling of long messages.

Add the pre-emptive generation to the `AgentSession` constructor:

    ```python
    preemptive_generation=True,
    ```

Compare the complete response latency before and after the change.

