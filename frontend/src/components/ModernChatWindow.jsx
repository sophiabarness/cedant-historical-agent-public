import { useState, useRef, useEffect } from 'react';

const ModernChatWindow = ({ 
  messages, 
  onSendMessage, 
  loading, 
  activeWorkflowId,
  onConfirmTool,
  pendingConfirmation,
  toolConfirmationData
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inputRef = useRef(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeWorkflowId || isSending) {
      return;
    }

    const messageToSend = inputMessage.trim();
    setInputMessage('');
    setIsSending(true);

    try {
      await onSendMessage(messageToSend);
    } catch (error) {
      console.error('Failed to send message:', error);
      setInputMessage(messageToSend);
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Focus management effect - only focus on initial mount
  useEffect(() => {
    // Focus input when component first mounts
    if (inputRef.current) {
      const timer = setTimeout(() => {
        inputRef.current.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [activeWorkflowId]); // Focus when workflow changes



  if (!activeWorkflowId) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🤖</div>
        <h3 style={{ fontSize: '1.2rem', fontWeight: '600', marginBottom: '0.5rem', color: '#4a5568' }}>
          No Active Workflow
        </h3>
        <p>Please start a workflow to begin chatting with the agent</p>
      </div>
    );
  }

  return (
    <>
      {/* Chat Header */}
      <div className="chat-header">
        <div className="chat-title">
          <span>💬</span>
          Conversation
        </div>
      </div>

      {/* Messages Container */}
      <div 
        ref={messagesContainerRef}
        className="chat-messages"
      >
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">💬</div>
            <h4 style={{ fontSize: '1.1rem', fontWeight: '600', marginBottom: '0.5rem', color: '#4a5568' }}>
              Ready to Chat
            </h4>
            <p>Start a conversation with your agent below</p>
          </div>
        ) : (
          messages.map((message, index) => (
            <MessageBubble 
              key={message.message_id || `msg-${index}`} 
              message={message} 
            />
          ))
        )}

        {/* Tool Confirmation Pending */}
        {pendingConfirmation && toolConfirmationData && (
          <div className="tool-confirmation">
            <div className="tool-confirmation-header">
              <span>🔧</span>
              Tool Confirmation Required
            </div>
            <p className="tool-confirmation-text">
              The agent wants to execute <strong>{toolConfirmationData.toolName}</strong>. Please review and confirm to proceed.
            </p>
            {toolConfirmationData.parameters && Object.keys(toolConfirmationData.parameters).length > 0 && (
              <div style={{
                background: '#f0f9ff',
                border: '1px solid #bae6fd',
                borderRadius: '6px',
                padding: '12px',
                margin: '8px 0',
                fontSize: '0.9em'
              }}>
                <div style={{ fontWeight: '600', marginBottom: '8px', color: '#0369a1' }}>
                  Arguments:
                </div>
                <pre style={{
                  background: '#f8fafc',
                  padding: '8px',
                  borderRadius: '4px',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: '0.85em',
                  margin: 0
                }}>
                  {JSON.stringify(toolConfirmationData.parameters, null, 2)}
                </pre>
              </div>
            )}
            <div className="tool-buttons">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onConfirmTool(true);
                  // Refocus input after confirmation
                  setTimeout(() => {
                    if (inputRef.current) {
                      inputRef.current.focus();
                    }
                  }, 200);
                }}
                className="btn btn-confirm"
              >
                ✅ CONFIRM TOOL
              </button>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  console.log(`❌ FRONTEND DEBUG: Cancel button clicked for tool: ${toolConfirmationData?.toolName}`)
                  console.log(`❌ FRONTEND DEBUG: Tool confirmation data:`, toolConfirmationData)
                  onConfirmTool(false);
                  // Refocus input after cancellation
                  setTimeout(() => {
                    if (inputRef.current) {
                      inputRef.current.focus();
                    }
                  }, 200);
                }}
                className="btn btn-cancel"
              >
                ❌ CANCEL
              </button>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Container */}
      <div className="chat-input-container">
        <form onSubmit={handleSubmit} className="chat-input-form">
          <textarea
            ref={inputRef}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message here..."
            className="chat-input"
            rows={1}
          />
          <button
            type="submit"
            disabled={!inputMessage.trim() || loading || isSending}
            className="send-button"
          >
            {isSending ? '⏳' : '📤'} Send
          </button>
        </form>
      </div>
    </>
  );
};

const MessageBubble = ({ message }) => {
  const isUser = message.actor === 'user';
  const isAgent = message.actor === 'agent';
  const isToolResult = message.actor === 'tool_result';
  
  let content = message.response;
  let displayContent = content;
  let isJson = false;
  let isToolConfirmation = false;
  let toolData = null;
  
  // Handle object responses
  if (typeof content === 'object' && content !== null) {
    // Check if this is a tool confirmation (has tool, args, next fields)
    if (content.tool && content.args && content.next === 'confirm') {
      isToolConfirmation = true;
      toolData = content;
      // Extract the response text for display
      displayContent = content.response || 'Tool execution requested';
    }
    // Check if this is a workflow completion confirmation (has next: 'confirm_completion')
    else if (content.next === 'confirm_completion' && content.type === 'workflow_completion') {
      isToolConfirmation = true;
      toolData = {
        tool: 'Complete Workflow',
        args: content.agent_result || {},
        response: content.response || 'Complete the workflow and return results'
      };
      displayContent = content.response || 'Complete the workflow and return results';
    }
    // For agent messages, try to extract the response text recursively
    else if (isAgent && content.response) {
      // If response is a string, use it
      if (typeof content.response === 'string') {
        displayContent = content.response;
      }
      // If response is still an object, try to extract further or stringify
      else if (typeof content.response === 'object' && content.response !== null) {
        // Check if there's a nested response field
        if (content.response.response && typeof content.response.response === 'string') {
          displayContent = content.response.response;
        } else {
          // Last resort: stringify the object
          isJson = true;
          displayContent = JSON.stringify(content.response, null, 2);
        }
      }
    } 
    // For tool results, format the JSON nicely
    else if (isToolResult) {
      isJson = true;
      displayContent = JSON.stringify(content, null, 2);
    }
    // For other objects, stringify
    else {
      isJson = true;
      displayContent = JSON.stringify(content, null, 2);
    }
  }

  // Determine the display name for agents
  const getAgentDisplayName = () => {
    if (!isAgent) return message.actor;
    
    // Priority 1: Check for agent_type in the message object (new format)
    if (message.agent_type) {
      return `🤖 ${message.agent_type}`;
    }
    
    // Priority 2: Check for agent_type in the response object (child workflow messages)
    if (typeof content === 'object' && content.agent_type) {
      return `🤖 ${content.agent_type}`;
    }
    
    // Priority 3: Check if the response string already contains agent identification (legacy format)
    if (typeof displayContent === 'string' && displayContent.includes('**') && displayContent.includes('Agent:**')) {
      // Extract agent name from the formatted string and remove it from display
      const match = displayContent.match(/\*\*([^*]+Agent)\*\*:\s*/);
      if (match) {
        // Remove the agent prefix from the display content
        displayContent = displayContent.replace(match[0], '');
        return `🤖 ${match[1]}`;
      }
    }
    
    // Fallback to generic agent
    return '🤖 Agent';
  };

  // Check if this is a cancellation message
  const isCancellation = message.actor === 'user_cancelled_tool_run' || message.actor === 'user_cancelled_completion';
  const isConfirmation = message.actor === 'user_confirmed_tool_run' || message.actor === 'user_confirmed_completion';

  return (
    <div className={`message-bubble ${isUser ? 'message-user' : isToolResult ? 'message-tool' : isCancellation ? 'message-cancellation' : isConfirmation ? 'message-confirmation' : 'message-agent'}`}>
      <div className="message-actor">
        {isUser ? '👤 You' : 
         isToolResult ? '🔧 Tool Result' : 
         isCancellation ? (message.actor === 'user_cancelled_completion' ? '❌ Workflow Cancelled' : '❌ Tool Cancelled') :
         isConfirmation ? (message.actor === 'user_confirmed_completion' ? '✅ Workflow Confirmed' : '✅ Tool Confirmed') :
         getAgentDisplayName()}
      </div>
      <div className="message-content">
        {isToolConfirmation ? (
          <div>
            <div style={{ marginBottom: '8px' }}>{displayContent}</div>
            <div style={{
              background: '#f0f9ff',
              border: '1px solid #bae6fd',
              borderRadius: '6px',
              padding: '12px',
              fontSize: '0.9em'
            }}>
              <div style={{ fontWeight: '600', marginBottom: '8px', color: '#0369a1' }}>
                🔧 Tool: {toolData.tool}
              </div>
              {toolData.args && Object.keys(toolData.args).length > 0 && (
                <div style={{ fontSize: '0.85em', color: '#475569' }}>
                  <strong>Arguments:</strong>
                  <pre style={{
                    background: '#f8fafc',
                    padding: '8px',
                    borderRadius: '4px',
                    marginTop: '4px',
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}>
                    {JSON.stringify(toolData.args, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ) : isJson ? (
          <pre style={{
            background: '#f5f5f5',
            padding: '12px',
            borderRadius: '6px',
            overflow: 'auto',
            fontSize: '0.85em',
            margin: 0,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word'
          }}>
            {displayContent}
          </pre>
        ) : (
          displayContent
        )}
      </div>
    </div>
  );
};

export default ModernChatWindow;