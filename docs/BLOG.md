# Trusting AI Agents: A Reinsurance Case Study

Demo: https://youtu.be/JeAwrzZC6TI?si=RQg9cHW7qJeATZBi

AI agents have the potential to automate tedious tasks such as manual data processing, but they are inherently non-deterministic and fallible. In the reinsurance industry, where data drives risk modeling and premium pricing, mistakes can have serious financial consequences. The more tools, agents, and multi-step decision making involved, the greater the chance of error. 

In this blog post, I share how I built a multi-agent system with human-in-the-loop safeguards to ensure accurate execution in the reinsurance domain.  

### Reinsurance 101

A single hurricane could bankrupt a home insurance company. To protect from such a loss, insurance companies purchase coverage for major catastrophes from reinsurance providers. In industry terminology, insurance companies that purchase reinsurance are called cedants.

### The Business Problem

Reinsurers have the challenge of ingesting claims data from cedants, modeling it to determine its risk, and pricing premiums. Claims data from cedants typically comes in the form of Excel submission packs that have no standardized format. 

Underwriters at my partner reinsurance company manually extract catastrophe loss events such as hurricanes or wildfires and loss amounts from cedant submission packs, manually link each loss event to an internal historical database and use this information to populate their internal cedant loss database. The process of extracting the data, linking, and populating the cedant loss database is manual, error-prone, and time consuming. This led me to create the following multi-agent AI system to accelerate the data population process.

### Agents and Tools

![Agent Architecture](agent-architecture.png)

At its core, the system converts messy Excel submission pack data into clean, structured catastrophe records. The process breaks down into four steps:  

- **Submission Pack Parser Agent:** Extracts catastrophe loss data (year, event name, loss amount) for each event from the Excel submission pack.
- **Historical Matcher:** Matches each catastrophe event to the corresponding historical event, if one exists. This tool spawns parallel child workflows which use fuzzy matching to check if there is a corresponding match.
- **Populate Cedant Data:** Creates cedant loss data records using the catastrophe loss data from the submission pack parser and historical matches.
- **Compare to Existing Cedant Data:** Identifies updates and additions compared to existing data from previous years.

Extracting catastrophe loss data from an Excel submission pack is itself a multi-step process. To handle this, I built the Submission Pack Parser agent which orchestrates the following tools:

- **Locate Submission Pack:** Given an ID, locates the file name of the submission pack.
- **Extract As Of Year:** Extracts the year the submission pack was last updated.
- **Sheet Identifier Agent:** Identifies the relevant catastrophe sheet in the Excel file.
- **Extract Catastrophe Data:** Extracts all catastrophe events, including the year, event name, and loss, from the identified sheet using LLM parsing. 

Sheet identification is non-trivial due to the large number of sheets in each workbook and the variability in submission pack formats. To accomplish this task, I made the Sheet Identifier agent, which has two tools: **Get Sheet Names** and **Read Sheet**. The agent’s prompting guides it to reason over sheet names first and selectively use the Read Sheet tool to inspect candidate sheets or a table-of-contents sheet when needed. Once it succeeds and receives user confirmation, it passes relevant sheet names back to the submission pack parser agent. 

In this architecture, we have two types of tools: **standard tools** and **agents-as-tools**. Standard tools, implemented via Temporal Activities, execute well-defined actions via code. Agents-as-tools, each with their own set of tools, start their own agent workflow that uses an LLM to determine the next tool execution. In this application, the LLM is used in two places: (1) to determine the next tool call in the agentic loop, (2) to extract catastrophe events from the identified sheets in the submission pack. 

### Why Agentic AI?

The process described above might seem rigid, which raises the question: why use AI agents instead of a fixed workflow? 

The simple answer is: flexibility. For example, in the Sheet Identification agent, every submission pack requires a different tool execution order. For some packs, reading sheet names is enough to identify the catastrophe sheet. For others, the agent must first read the table of contents, or inspect candidate sheets to verify which contains the actual data. Some packs have no table of contents. Some split catastrophe data across multiple sheets. Hard-coding all the possible execution paths quickly becomes hard to maintain. 

An agentic AI-based system allows the agent to decide the next step based on its context: previous tool results, prompting, and user interaction. It can also re-execute a tool if needed. Choosing the next step dynamically, rather than following a fixed order, lets the system adapt to new submission packs and incorporate human context into decision-making. It also enables graceful recovery. If a tool fails or returns ambiguous results, the agent can reason about the error and proactively ask the user for guidance rather than  crashing.

### Why Multiple Agents?

I could have implemented this system with a single agent that had all the tools. However, the more choices an agent has, the more likely it is to get confused about which tool to execute next. Longer prompts and excessive context lead to higher token usage and slow down execution. 

Breaking the process into **multiple modular agents** ensures that each agent focuses on a specific goal. Each agent only needs to reason about a limited set of tools and the relevant context. For example, the Populate Cedant Data tool needs to know that the Submission Pack Parser agent completed successfully, but details like all the sheet names extracted are irrelevant. By separating agents, we enable natural context management and avoid overwhelming the LLM with unnecessary information. 

This architecture requires coordinating multiple agents that can pause for human input, pass data between each other, and recover gracefully from failures. With this design in mind, let's look at how to implement the system. 

### Implementing an agent with human in the loop

We implement the agents using Temporal. Each agent runs as a **Temporal workflow**, with LLM calls and tool executions handled via **Temporal activities**.

Each agent is configured with an `AgentGoal` specifying its tools, description, starter prompt, and example conversation history:

```python
@dataclass
class AgentGoal:
    agent_name: str
    tools: List[ToolDefinition]
    description: str
    starter_prompt: str
    example_conversation_history: str
```

Agents run a loop where they call the LLM with a prompt containing the `AgentGoal`, past conversation history, user input, and the tool completion prompt. At each iteration, the LLM decides if it wants to execute a tool, if it's ready for agent completion, or whether it needs to request human input. 

![Implementation HITL](implementation-HITL.png)

To prevent the agent from spiraling or making mistakes, a human confirms or cancels **each tool execution and agent completion**. The human can also intervene at any point with direct input. This is implemented using **Temporal signals**: when a user confirms a tool execution or agent completion, a signal is sent to the Agent Workflow, and the agentic loop blocks until it receives user confirmation. When a user intervenes with a prompt, the agentic loop processes the prompt to determine the next best action. 

### Multiple agents with human in the loop

To support multiple agents, each agent creates its own instance of the Agent Goal Workflow with its own `AgentGoal`.

The **Bridge Workflow** ties all the agents together by acting as a central router. It keeps track of which agent is currently active, and routes user prompts, tool confirmations, workflow completions, and cancellations to the active agent. When we switch to a new agent, the Bridge Workflow updates its references to point to the new Agent Workflow to ensure user interactions get routed to the correct active agent. 

The Bridge Workflow also serves as the **inter-agent data store**. When there is data to pass between agents, activities signal the Bridge Workflow to save their results and later query it to retrieve them. For example, the Extract Catastrophe Data tool from the Submission Pack Parser agent typically extracts between 10 and 100 events, which is too much data for an LLM’s conversation history. Instead, we save the extracted data to the inter-agent data store and the Historical Matcher and Populate Cedant Data tools query when needed. Temporal Workflows are well-suited for this use case because they persist inter-agent state reliably over time. Since the data we pass between agents and the conversation histories are small (less than 2 MB), we save it in the workflow rather than using an external data store. 

### Principles for building AI Agents

Here are some design principles I discovered while building this system: 

(1) **Design for human-in-the-loop**. Agents make mistakes. Providing human input and confirmation helps ensure the agent stays on track. In this architecture, the core purpose of the Bridge Workflow is to route human-in-the-loop interactions to the appropriate sub-agents. 

(2) **Use modular subagents**. Subagents keep the LLM focused on a specific task and separate relevant context. 

(3) **Keep tool arguments simple**. More options confuse the LLM. As an example, my original ReadSheet tool provided an argument for the LLM to choose how many rows to read. I simplified it to two options to make it more performant: a preview (first 20 rows) or full (entire sheet). 

### Conclusion

Temporal’s durable execution allows agents to operate reliably. Workflows and activities make it straightforward to implement agent logic and tool execution. Automatic retries ensure the system continues operating in face of LLM call or tool failure. Signals and queries make human-in-the-loop and inter-agent communication simple. Temporal’s UI observability makes every agent action, signal, and update visible in the workflow history. 

The foundation of trust in this system comes from the human-in-the-loop functionality. By allowing the user to interject at any point, the user retains control over the agent's execution. User confirmation for tool calls and agent completions ensures the user knows what the agent will do ahead of time. With human-in-the-loop, the system shifts from a black-box executing autonomously to a supervised assistant. 

While this proof-of-concept project focused on a reinsurance use case, the underlying design principles apply more broadly for other multi-agent applications requiring careful human supervision.  

Check out the code here: https://github.com/sophiabarness/cedant-historical-agent-public
