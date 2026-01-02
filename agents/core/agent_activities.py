"""Core agent activities for LLM integration.

This module contains the core AgentActivities class that is used throughout 
the agent hierarchy for LLM integration and workflow execution.
"""

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from litellm import completion
from temporalio import activity

from models.requests import ToolPromptInput

load_dotenv(override=True)


class AgentActivities:
    """Activities class for handling LLM integration and tool execution."""

    def __init__(self):
        """Initialize LLM client using LiteLLM."""
        # Use fast model for agent activities
        self.llm_model = os.environ.get("LLM_MODEL_FAST", os.environ.get("LLM_MODEL"))
        self.llm_key = os.environ.get("LLM_KEY")
        self.llm_base_url = os.environ.get("LLM_BASE_URL")
        activity.logger.info(
            f"Initializing AgentActivities with LLM model: {self.llm_model}"
        )
        if self.llm_base_url:
            activity.logger.info(f"Using custom base URL: {self.llm_base_url}")

    @activity.defn
    async def agent_toolPlanner(self, input: ToolPromptInput) -> dict:
        """
        LLM activity for tool selection and planning.
        
        This activity processes user prompts and determines which tools to use
        and what arguments are needed for tool execution.
        
        Args:
            input: ToolPromptInput containing prompt and context instructions
            
        Returns:
            dict: Tool execution plan with next steps, tool name, and arguments
        """
        activity.logger.info(f"Tool Planner: Processing prompt: {input.prompt[:100]}...")
        
        messages = [
            {
                "role": "system",
                "content": input.context_instructions
                + ". The current date is "
                + datetime.now().strftime("%B %d, %Y"),
            },
            {
                "role": "user",
                "content": input.prompt,
            },
        ]

        try:
            activity.logger.info(f"Calling LLM ({self.llm_model})...")
            completion_kwargs = {
                "model": self.llm_model,
                "messages": messages,
                "api_key": self.llm_key,
                "max_tokens": 4096,
            }

            if self.llm_base_url:
                completion_kwargs["base_url"] = self.llm_base_url

            response = completion(**completion_kwargs)

            response_content = response.choices[0].message.content
            activity.logger.info(f"LLM response received ({len(response_content)} chars)")
            activity.logger.debug(f"Full response: {response_content}")

            response_content = self.sanitize_json_response(response_content)
            result = self.parse_json_response(response_content)
            
            next_step = result.get("next", "unknown")
            tool = result.get("tool", "none")
            activity.logger.info(f"Decision: next={next_step}, tool={tool}")
            
            return result
            
        except Exception as e:
            activity.logger.error(f"Error in LLM completion: {str(e)}")
            raise

    def sanitize_json_response(self, response_content: str) -> str:
        """Remove markdown code block markers from LLM response."""
        return response_content.replace("```json", "").replace("```", "").strip()

    def parse_json_response(self, response_content: str) -> dict:
        """Parse JSON response from LLM."""
        if not response_content or not response_content.strip():
            activity.logger.error("Empty response from LLM")
            return {
                "next": "question",
                "response": "I received an empty response from the LLM. Please try again.",
                "tool": None,
                "args": {}
            }
        
        try:
            return json.loads(response_content)
        except json.JSONDecodeError as e:
            activity.logger.error(f"JSON parse failed at pos {e.pos}: {e.msg}")
            activity.logger.error(f"Response content: {response_content[:500]}...")
            return {
                "next": "question", 
                "response": "JSON parsing failed. Please check logs for full response.",
                "tool": None,
                "args": {}
            }



