"""AgentExecutor - orchestrates the BUPA Sync Agent's LangGraph workflow."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration

from app.agent import create_agent
from app.mcp_tools import get_mcp_tools
from app.util import get_system_prompt, get_logger

logger = get_logger(__name__)

# Path to shared settings file (managed by backend UI)
SETTINGS_PATH = Path(
    os.environ.get(
        "SETTINGS_PATH",
        str(
            Path(__file__).parent.parent.parent.parent
            / "backend"
            / "data"
            / "settings.json"
        ),
    )
)


def _load_llm_settings() -> dict:
    """Load LLM configuration from shared settings.json file.

    Resolution order:
    1. Production mode: environment variables only.
    2. Local/Docker mode: settings.json -> env var overrides -> hardcoded defaults.

    Environment variables (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY, LLM_PROVIDER)
    always override settings.json values when set, ensuring Docker containers
    work correctly even before the user configures via the Settings UI.
    """
    defaults = {
        "provider": "local_proxy",
        "base_url": "http://localhost:6655/litellm/v1",
        "model": "anthropic--claude-4.6-sonnet",
        "api_key": "",
    }

    # Production mode: use env vars exclusively
    if os.environ.get("DEPLOYMENT_MODE") == "production":
        return {
            "provider": os.environ.get("LLM_PROVIDER", "sap_ai_core"),
            "base_url": os.environ.get("LLM_BASE_URL", ""),
            "model": os.environ.get("LLM_MODEL", ""),
            "api_key": os.environ.get("LLM_API_KEY", ""),
        }

    # Local/Docker mode: read from settings.json first
    config = dict(defaults)
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r") as f:
                settings = json.load(f)
            llm_config = settings.get("llm", {})
            config = {
                "provider": llm_config.get("provider", defaults["provider"]),
                "base_url": llm_config.get("base_url", defaults["base_url"]),
                "model": llm_config.get("model", defaults["model"]),
                "api_key": llm_config.get("api_key", defaults["api_key"]),
            }
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not read settings.json: {e}. Using defaults.")

    # Environment variables override settings.json (critical for Docker mode
    # where localhost doesn't resolve to the host machine)
    if os.environ.get("LLM_BASE_URL"):
        config["base_url"] = os.environ["LLM_BASE_URL"]
    if os.environ.get("LLM_MODEL"):
        config["model"] = os.environ["LLM_MODEL"]
    if os.environ.get("LLM_API_KEY"):
        config["api_key"] = os.environ["LLM_API_KEY"]
    if os.environ.get("LLM_PROVIDER"):
        config["provider"] = os.environ["LLM_PROVIDER"]

    return config


class LiteLLMChat(BaseChatModel):
    """LangChain-compatible LLM wrapper that routes to local proxy or SAP AI Core.

    Supports the Hyperspace LLM Proxy (OpenAI-compatible endpoint) for local dev
    and SAP AI Core for production deployment.
    """

    model_name: str = "anthropic--claude-4.6-sonnet"
    api_base: str = "http://localhost:6655/litellm/v1"
    api_key: str = ""

    @property
    def _llm_type(self) -> str:
        return "litellm"

    async def _agenerate(self, messages, stop=None, **kwargs):
        from litellm import acompletion
        import litellm

        formatted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                formatted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                formatted.append({"role": "assistant", "content": msg.content})
            else:
                formatted.append({"role": "user", "content": str(msg.content)})

        # LiteLLM requires "openai/" prefix for custom OpenAI-compatible endpoints
        model = self.model_name
        if not any(
            model.startswith(p) for p in ("openai/", "anthropic/", "gemini/", "azure/")
        ):
            model = f"openai/{model}"

        try:
            response = await acompletion(
                model=model,
                messages=formatted,
                api_base=self.api_base,
                api_key=self.api_key or "not-needed",
                stop=stop,
                **kwargs,
            )
        except litellm.AuthenticationError as e:
            logger.error(
                f"LLM authentication failed. Check API key in Settings > LLM. "
                f"Provider endpoint: {self.api_base}. Error: {e}"
            )
            raise RuntimeError(
                f"LLM authentication failed. Please update the API key in "
                f"Dashboard Settings > LLM section and ensure the LLM proxy is "
                f"running at {self.api_base}. "
                f"(If using Docker, verify the Hyperspace proxy is running on your host machine.)"
            ) from e
        except litellm.APIConnectionError as e:
            logger.error(f"Cannot reach LLM proxy at {self.api_base}. Error: {e}")
            raise RuntimeError(
                f"Cannot connect to LLM proxy at {self.api_base}. "
                f"Ensure the Hyperspace LLM proxy is running. "
                f"(If using Docker, the proxy must be accessible at host.docker.internal:6655.)"
            ) from e

        content = response.choices[0].message.content or ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )

    def _generate(self, messages, stop=None, **kwargs):
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._agenerate(messages, stop=stop, **kwargs)
            )
        finally:
            loop.close()


class AgentExecutor:
    """Manages the LangGraph agent lifecycle and message processing."""

    def __init__(self):
        self._graph = None
        self._tools = None
        self._initialized = False

    async def _create_llm(self) -> BaseChatModel | None:
        """Create LLM instance based on settings configuration.

        Supports:
        - local_proxy: Hyperspace LLM Proxy at localhost:6655 (OpenAI-compatible)
        - sap_ai_core: SAP AI Core deployment (production)
        """
        config = _load_llm_settings()
        provider = config["provider"]

        logger.info(
            f"Creating LLM with provider={provider}, model={config['model']}, base_url={config['base_url']}"
        )

        try:
            if provider == "sap_ai_core":
                # SAP AI Core uses the same LiteLLM interface but different base URL
                llm = LiteLLMChat(
                    model_name=config["model"],
                    api_base=config["base_url"],
                    api_key=config["api_key"],
                )
            else:
                # Local proxy (default) - Hyperspace LLM Proxy
                llm = LiteLLMChat(
                    model_name=config["model"],
                    api_base=config["base_url"],
                    api_key=config["api_key"] or "not-needed",
                )

            # Verify LLM is reachable by calling /models endpoint
            import httpx

            models_url = config["base_url"].rstrip("/") + "/models"
            headers = (
                {"Authorization": f"Bearer {config['api_key']}"}
                if config["api_key"]
                else {}
            )
            try:
                resp = httpx.get(models_url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    logger.info(f"LLM verified reachable: {provider}/{config['model']}")
                    return llm
                elif resp.status_code == 401:
                    logger.warning(
                        f"LLM proxy returned 401 (invalid API key). "
                        f"The agent will attempt to use the LLM but calls may fail. "
                        f"Update the API key in Dashboard Settings > LLM."
                    )
                    # Still return the LLM so the user gets a clear auth error
                    # at invocation time rather than silent mock mode
                    return llm
                else:
                    logger.warning(
                        f"LLM endpoint returned {resp.status_code}. Running in mock mode."
                    )
                    return None
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"LLM proxy not reachable ({e}). Running in mock mode.")
                return None

        except Exception as e:
            logger.warning(
                f"Failed to create LLM ({provider}): {e}. Agent will run without LLM."
            )
            return None

    async def initialize(self):
        """Initialize the agent with MCP tools and LLM configuration."""
        if self._initialized:
            return

        logger.info("Initializing AgentExecutor...")

        # Lazy load MCP tools from Agent Gateway
        self._tools = await get_mcp_tools()
        logger.info(f"Loaded {len(self._tools)} MCP tools")

        # Create the LLM instance - supports both local proxy and SAP AI Core
        # Configuration is read from shared settings.json (managed by backend UI)
        llm = await self._create_llm()

        # Create the LangGraph agent
        system_prompt = get_system_prompt()
        self._graph = create_agent(
            llm=llm, tools=self._tools, system_prompt=system_prompt
        )
        self._initialized = True
        self._last_llm_config = _load_llm_settings()
        logger.info("AgentExecutor initialized successfully")

    async def _refresh_llm(self):
        """Re-read LLM settings and rebuild the agent if config changed.

        This allows the user to update the API key in the Settings UI
        without needing to restart the agent container.
        """
        current_config = _load_llm_settings()
        if current_config != getattr(self, "_last_llm_config", None):
            logger.info(
                "LLM settings changed (base_url or api_key updated). Rebuilding agent..."
            )
            llm = await self._create_llm()
            system_prompt = get_system_prompt()
            self._graph = create_agent(
                llm=llm, tools=self._tools, system_prompt=system_prompt
            )
            self._last_llm_config = current_config
            logger.info("Agent rebuilt with updated LLM configuration.")

    async def invoke(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Process incoming messages through the LangGraph agent.

        Re-reads LLM settings on each invocation so that API key updates
        from the Settings UI take effect without restarting the agent.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.

        Returns:
            Dict with the agent's response content.
        """
        if not self._initialized:
            await self.initialize()
        else:
            # Re-read LLM settings in case user updated API key via Settings UI
            await self._refresh_llm()

        # Convert incoming messages to LangChain message objects
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        logger.info(f"Processing {len(lc_messages)} messages through agent graph")

        # Invoke the LangGraph agent with timeout protection
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke({"messages": lc_messages}),
                timeout=120.0,  # 2 minute timeout per invocation
            )

            # Extract the final AI message from the result
            output_messages = result.get("messages", [])
            if output_messages:
                final_message = output_messages[-1]
                return {
                    "role": "assistant",
                    "content": final_message.content
                    if hasattr(final_message, "content")
                    else str(final_message),
                }

            return {"role": "assistant", "content": "No response generated."}

        except asyncio.TimeoutError:
            logger.error("Agent invocation timed out after 120 seconds")
            return {
                "role": "assistant",
                "content": "Request timed out. The error batch may be too large. Try reducing the batch size.",
            }
        except Exception as e:
            logger.exception("Error during agent invocation")
            return {
                "role": "assistant",
                "content": f"An error occurred while processing your request: {str(e)}",
            }
