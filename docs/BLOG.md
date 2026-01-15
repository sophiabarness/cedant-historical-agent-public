# Trusting AI Agents: A Reinsurance Case Study

Demo: https://youtu.be/NkQ8bA3AcAQ?si=Mbz7bhkbJX3Go6A2

[AI agents](https://temporal.io/blog/a-mental-model-for-agentic-ai-applications) have the potential to automate tedious tasks such as manual data processing, but they’re inherently non-deterministic and fallible. In the reinsurance industry, where data drives risk modeling and premium pricing, mistakes can have serious financial consequences. And the more tools, agents, and multi-step decision-making involved, the greater the chance of error. 

In this blog post, I’ll share how I built a multi-agent system with human-in-the-loop safeguards to ensure accurate execution in the reinsurance domain.  

### Reinsurance 101

A single hurricane could bankrupt a home insurance company. To protect against that kind of loss, insurance companies purchase coverage for major catastrophes from reinsurance providers. In industry terminology, insurance companies that purchase reinsurance are called *cedants*.

### The Business Problem

Reinsurers face the challenge of ingesting claims data from cedants, modeling it to determine its risk, and pricing premiums. Claims data from cedants typically comes in the form of Excel submission packs, and there’s no standardized format. 

Underwriters at my partner reinsurance company manually extract catastrophe loss data from cedant submission packs, link each loss event to an internal historical database, and use this information to populate their internal cedant loss database. All that extracting, linking, and populating is manual and time-consuming. This led me to build the following multi-agent AI system to speed things up.

### Agents and Tools

![Agent Architecture](agent-architecture.png)

At its core, the system converts messy Excel submission pack data into clean, structured catastrophe records. The process breaks down into four steps:  

- **Submission Pack Parser Agent:** Extracts catastrophe loss data from the Excel submission pack.
- **Historical Matcher:** Matches each catastrophe event to the corresponding historical event, if one exists. This tool spawns parallel child Workflows which use fuzzy matching.
- **Populate Cedant Data:** Creates cedant loss data records using the data from the submission pack parser and historical matches.
- **Compare to Existing Cedant Data:** Flags new records and changes compared to existing data.

Extracting catastrophe loss data from an Excel submission pack is itself a multi-step process. The *Submission Pack Parser* agent orchestrates the following tools:

- **Locate Submission Pack:** Given an ID, locates the filename of the submission pack.
- **Extract As Of Year:** Extracts the year the submission pack was last updated.
- **Sheet Identifier Agent:** Identifies the relevant catastrophe sheet in the Excel file.
- **Extract Catastrophe Data:** Extracts all catastrophe events, including the year, event name, and loss amount, from the identified sheet using LLM parsing. 

Sheet identification is nontrivial. There are often many sheets in each workbook, and submission pack formats vary widely. The Sheet Identifier agent handles this with two tools: **Get Sheet Names** and **Read Sheet**. Prompting guides the agent to check sheet names first, look for a table of contents, and inspect candidate sheets as needed. Once it succeeds and receives user confirmation, it passes the relevant sheet names back to the Submission Pack Parser agent. 

In this architecture, we have two types of tools: **standard tools** and **agents-as-tools**. Standard tools, implemented as Temporal Activities, execute well-defined actions in code. Agents-as-tools, each with their own set of tools, start a separate *Agent Workflow* that uses an LLM to determine the next tool execution. In this application, the LLM is used in two places: 
1. to determine the next action in the agentic loop, 
2. to extract catastrophe events from the identified sheets. 

### Why Agentic AI?

The process I just described might seem pretty rigid, which raises the question: why use AI agents instead of a fixed workflow? 

The simple answer is flexibility. In the *Sheet Identifier* agent, for example, every submission pack requires a different tool execution order. For some packs, reading sheet names is enough to identify the catastrophe sheet. For others, the agent has to first read the table of contents or inspect candidate sheets to verify which one actually contains the data. Some packs have no table of contents at all. Some split catastrophe data across multiple sheets. Hard-coding all these possible paths becomes unmaintainable fast. 

An agentic approach lets the agent decide its next step based on context: previous tool results, prompting, and user interaction. It can also re-execute a tool if needed. Choosing the next step dynamically, rather than following a fixed order, lets the system adapt to new submission packs and incorporate human context into its decisions. It also enables graceful recovery. If a tool fails or returns ambiguous results, the agent can reason about the error and proactively ask the user for guidance rather than just crashing.

### Why Multiple Agents?

I could’ve implemented this system with a single agent that had all the tools. But the more choices an agent has, the more likely it is to get confused about which tool to execute next. Longer prompts and excessive context also lead to higher token usage and slower execution. 

Breaking the process into **multiple modular agents** ensures each one focuses on a specific goal. Each agent only needs to reason about a limited set of tools and the relevant context. For example, the *Populate Cedant Data* tool needs to know that the *Submission Pack Parser* agent completed successfully, but details like the specific sheet names extracted are irrelevant. Separating agents enables natural context management and avoids overwhelming the LLM with unnecessary information. 

This architecture requires coordinating multiple agents that can pause for human input, pass data between each other, and recover gracefully from failures. With this design in mind, let’s look at how to actually implement it.

### Implementing an Agent with Human-in-the-Loop

We implement the agents using Temporal. Each agent runs as a [**Temporal Workflow**](https://docs.temporal.io/workflows), with LLM calls and tool executions handled via [**Temporal Activities**](https://docs.temporal.io/activities).

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

Agents run a loop where they call the LLM with a prompt containing the `AgentGoal`, past conversation history, user input, and the tool completion prompt. At each iteration, the LLM decides whether to execute a tool, signal agent completion, or request human input. 

![Implementation HITL](implementation-HITL.png)

To prevent the agent from spiraling or making mistakes, a human confirms or cancels **each tool execution and agent completion**. The human can also intervene at any point with direct input. This is implemented using **Temporal Signals**: when a user confirms a tool execution or agent completion, a Signal is sent to the *Agent Workflow*, and the agentic loop blocks until it receives that confirmation. When a user intervenes with a prompt, the loop processes it to determine the next best action. As an example, the *Extract Catastrophe Data* tool takes `user_input` as a direct argument, so the tool’s LLM call can incorporate additional context beyond the default prompt when needed.


### Multiple Agents with Human-in-the-Loop

To support multiple agents, each one runs as its own instance of the *Agent Workflow* with its own `AgentGoal`.

The **Bridge Workflow** ties all the agents together by acting as a central router. It keeps track of which agent is currently active and routes user prompts, tool confirmations, Workflow completions, and cancellations to the active agent. When we switch to a new agent, the *Bridge Workflow* updates its references to point to the new *Agent Workflow*, ensuring user interactions get routed correctly. 

We leverage the Bridge Workflow’s state as an **inter-agent data store**. When data needs to pass between agents, an Activity in one agent signals the *Bridge Workflow* to save the results, and Activities in other agents query it to retrieve them. For example, the *Extract Catastrophe Data* tool from the *Submission Pack Parser* agent typically pulls between 10 and 100 events from the submission pack, which is too much for an LLM’s conversation history. Instead, we save the extracted data to the inter-agent data store, and the *Historical Matcher* and *Populate Cedant Data* tools query it when needed. Temporal Workflows are well-suited for this use case because they persist inter-agent state reliably over time. Since both the data we pass between agents and the conversation histories are small (under 2 MB), we save them directly in the Workflow rather than reaching for an external data store.

### Principles for Building AI Agents

Here are some design principles I discovered while building this system: 

(1) **Design for human-in-the-loop**. Agents make mistakes. Providing human input and confirmation helps keep the agent on track. In this architecture, the core purpose of the *Bridge Workflow* is to route human-in-the-loop interactions to the appropriate sub-agent.

(2) **Use modular subagents**. Sub-agents keep the LLM focused on a specific task and isolate relevant context. 

(3) **Keep tool arguments simple**. More options confuse the LLM. My original *ReadSheet* tool, for example, let the LLM choose how many rows to read. I simplified it to just two options: a preview mode (first 20 rows) or full mode (entire sheet). The result? Much more performant. 

### Conclusion

Temporal’s [Durable Execution](https://temporal.io/blog/what-is-durable-execution) allows agents to operate reliably. Workflows and Activities make it straightforward to implement agent logic and tool execution. Automatic retries keep the system running in the event of LLM call or tool failure. Signals and Queries make human-in-the-loop and inter-agent communication simple. And Temporal’s UI observability makes every agent action, Signal, and update visible in the Workflow history.

The foundation of trust in this system comes from the human-in-the-loop functionality. By allowing the user to interject and influence how tools are executed, the user retains control over the agent. Confirming tool calls and agent completions ensures the user knows what the agent will do ahead of time. With human-in-the-loop, the system shifts from a black box executing autonomously into a supervised assistant.

While this proof-of-concept project focused on a reinsurance use case, the underlying design principles apply more broadly to other multi-agent applications requiring careful human supervision. 

Check out the code here: https://github.com/sophiabarness/cedant-historical-agent-public
