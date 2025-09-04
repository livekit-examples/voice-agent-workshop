# Add funcion c

In this exercise, we'll add function tools to the agent.

Step 1: Add the import to the `agent.py` file:

    ```python
    from livekit.agents.llm import function_tool
    from livekit.agents import RunContext
    ```

Step 2: Add a simple function tool to the `Assistant` class:

    ```python
    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.
        
        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."


    