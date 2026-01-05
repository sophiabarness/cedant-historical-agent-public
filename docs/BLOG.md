# Trusting AI Agents: A Reinsurance Case Study

Demo: https://youtu.be/JeAwrzZC6TI?si=RQg9cHW7qJeATZBi

AI agents can automate tedious tasks such as manual data processing, but they are inherently non-deterministic and fallible. In the reinsurance industry, where data drives risk modeling and premium pricing, mistakes have serious financial consequences. The more tools, agents, and multi-step decision making involved, the greater the chance of error. 

In this blog post, I share how I built a multi-agent system with human-in-the-loop safeguards to ensure accurate execution in the reinsurance domain.  

### Reinsurance 101

A single hurricane could bankrupt a home insurance company. To protect themselves from such a loss, insurance companies purchase reinsurance for major catastrophes from reinsurance providers, who diversify their portfolios across regions. In industry lingo, the insurance companies that reinsurers insure are called cedants. 

### The Business Problem

Reinsurers have the challenge of taking claims data from cedants, modeling it to determine its risk, and pricing premiums. Claims data from cedants typically comes in the form of Excel submission packs that have no standardized format. 

Underwriters at my partner reinsurance company manually extract catastrophe loss events such as hurricanes or wildfires and loss amounts from Excel submission packs provided (typically ranging from 10-100 events), manually link each loss event to an internal historical database and use this information to populate their internal cedant loss database. The process of extracting the data, linking, and populating the cedant loss database is manual, error-prone, and time consuming. This led me to create the following multi-agent AI system to accelerate the data population process.

### Agents and Tools

![Agent Architecture](agent-architecture.png)

Let’s break down the business problem into concrete steps. At a high level, the process consists of:  

- **Submission Pack Parser Agent:** Extracts catastrophe loss data (year, event name, loss amount) for each event from Excel submission pack.
- **Historical Matcher:** Matches each catastrophe event to the corresponding historical event, if one exists. This tool spawns parallel child workflows for each event which do fuzzy matching to find if there is a corresponding historical event.
- **Populate Cedant Data:** Uses the catastrophe loss data from the submission pack parser and historical matches to populate the internal cedant data loss database.
- **Compare to Extisting Cedant Data:** Identifies updates and additions compared to existing data from previous years.

Extracting catastrophe loss data from a generic Excel submission pack is itself a multi-step process. To handle this, I built the Submission Pack Parser agent with the following tools:

- **Locate Submission Pack:** Given an ID, locates the file name of the submission pack
- **Extract As Of Year:** Extracts the year from the submission pack for the Cedant Loss Data table
- **Sheet Identifier Agent:** Identifies the relevant catastrophe sheet in the Excel file
- **Extract Catastrophe Data:** Extracts all catastrophe events, including the year, event name, and loss, from the identified sheet using LLM parsing. 

The sheet identification step is non-trivial due to the variety of different submission pack formats and the number of sheets (typically at least 15). So, I made a dedicated Sheet Identification agent for this goal. This agent has two tools: **Get Sheet Names** and **Read Sheet**. The agent's prompting guides it to use the Get Sheet Names tool to first find the sheet names and then use the Read Sheet tool to retrieve the contents of potential sheets or the table of contents sheet. Once it succeeds and receives user confirmation, it passes relevant sheet names back to the submission pack parser agent. 

In this architecture, we have two types of tools: **standard tools** and **agents-as-tools**. Standard tools, implemented via Temporal Activities, execute well-defined actions via code. Agents-as-tools, each with their own set of tools, start their own Agent workflow that use an LLM to determine the next tool execution. In this entire application, the LLM is used in two places: (1) to determine the next tool call in the agentic loop for agents (2) to parse the catastrophe events, year, and loss amount from identified sheets in the Extract Catastrophe Data tool. 

### Why Agentic AI?

The process described above might seem rigid, which raises the question: why use AI agents to orchestrate this process instead of a fixed workflow? 

The simple answer is: flexibility and adaptability. As an example, suppose a non-standard submission pack format needs to be parsed. The Sheet Identification agent might not find a table of contents sheet to guide its decision-making. In this case, the agent can use its tools, *ReadSheet* and *GetSheetNames,* to make an intelligent decision based on the contents of strong candidate sheets. If it’s unsure, it can ask the human for help and use that input for a final decision. 

An agentic AI-based system allows the agent to decide the next step based on its context: previous tool results, prompting, and user interaction. It can also re-execute a tool if needed. Choosing the next step dynamically, rather than following a fixed order, lets the system adapt to unpredictable situations and incorporate its context into decision-making.

### Why Multiple Agents?

I could have implemented this system with a single agent that had all the tools, which would have been much simpler. However, giving one agent too many tools leads to **prompting overwhelm**. The more choices an agent has, the more likely it is to get confused about which tool to execute next. Longer prompts and excessive context increase the chance the LLM “forgets” important details, lead to higher token usage, and slow down execution. 

Breaking the process into **multiple modular agents** ensures that each agent focuses on a specific goal. Each agent only needs to reason about a limited set of tools and the relevant context. For example, the Populate Cedant Data tool needs to know that the Submission Pack Parser agent completed successfully, but details like all the sheet names extracted are irrelevant. By separating agents in this way, we enable natural context management and avoid overwhelming the LLM with unnecessary information. 

### Implementing an agent with human in the loop

Each agent runs a **Temporal workflow** and has its own `AgentGoal`configuration specifying tools, description, starter prompt, and example conversation history:

```
@dataclass
class AgentGoal:
    agent_name: str
    tools: List[ToolDefinition]
    description: str
    starter_prompt: str
    example_conversation_history: str
```

Agents run a loop where they call the LLM with a prompt containing the `AgentGoal`, past conversation history, any user prompt, and the tool completion prompt (if a tool just finished executing). At each iteration, the LLM decides if it want to execute a tool, if it's ready for agent completion, or whether it needs to request human input.

![Implementation HITL](implementation-HITL.png)

To avoid the agent from spiraling or making mistakes, a human confirms or cancels **each tool execution and agent completion**. The human can also intervene at any point with direct input. This is implemented using **Temporal signals**: when a user confirms a tool execution, a signal is sent to the Agent Workflow, and the agentic loop blocks the tool execution until it receives the tool confirmation. 

This **human in the loop functionality** ensures that the agent can achieve its goals even if part of the agent produces uncertain results.

### Multiple agents with human in the loop

To support multiple agents, each agent creates its own instance of the Agent Goal Workflow with its own `AgentGoal`. Each Agent Goal Workflow tracks its parent agent (to return to on completion) and pending child agents. 

To allow humans to interact with any sub-agent (not just the supervisor agent), I added a **Bridge Workflow.** The Bridge aggregates messages from all the agents for the frontend. It also keeps track of which agent is currently active, and routes user prompts, tool confirmations, workflow completions, and cancellations to the active agent. Referencing the diagram, the Bridge Workflow will switch out the current Agent Workflow to the one that the user is interacting with to ensure user interatctions are getting routed to the correct active agent. 

The Bridge Workflow also serves as the **inter-agent data store**. When there is data to pass between agents, activities can signal the Bridge Workflow to save their results and later query it to retrieve them. For example, the Catastrophe Loss Events tool from the Submission Pack Parser agent typically extracts between 10 and 100 events, which is too much data for an LLM’s conversation history. Instead, we save the extracted data to the inter-agent data store and the Historical Matcher and Populate Cedant Data tools query when needed. Temporal Workflows are well-suited for this use case because they can persist inter-agent state reliably over time. Since the data we pass between agents and conversation history is small (less than 2 MB), we can save it in the workflow rather than using a proper external data store. 

### Principles for building AI Agents

Here are some important design principles I discovered while building this system: 

(1) **Design for human-in-the-loop**. Agents can make mistakes. Providing human input and confirmation at core stages helps ensure the agent stays on track. In this architecture, the core purpose of the Bridge Workflow is to route human-in-the-loop interactions to the appropriate sub-agents. 

(2) **Use modular subagents**. Subagents keep the LLM focused on a specific task and separate relevant context. Temporal Workflow state can be used to pass data between agents and store agent-specific information such as conversation history. 

(3) **Keep tool arguments simple**. More options confuse the LLM. As an example, my original ReadSheet tool allowed the LLM to choose how many rows to read. I simplified it to two options to make it more performant: a preview (first 20 rows) or full (entire sheet). 

(4) **Minimize latency.** LLM calls take time, and users are impatient.  Every additional LLM call can improve results but adds latency. In practice, for the Sheet Identification Agent, I prompted it to make its best guess after only reading the Table of Contents sheet rather than reading all candidate sheets. 


### Conclusion

Temporal’s durable execution allows agents to operate reliably. Workflows and activities make it straightforward to implement agent logic and tool execution, while automatic retries ensure the system continues operating in face of tool failure. Signals and queries make human-in-the-loop and inter-agent communication simple. Temporal’s UI observability makes every agent action, signal, and update visible in the workflow history. 

While this proof-of-concept project focused on a reinsurance use case, the underlying design principles apply more broadly for other multi-agent applications requiring careful human supervision.  

You can dive into the code on GitHub: https://github.com/sophiabarness/cedant-historical-agent-public
