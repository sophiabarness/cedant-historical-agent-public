import { useState, useEffect, useCallback, useRef } from 'react'
import './styles/modern.css'
import ModernChatWindow from './components/ModernChatWindow'
import apiService from './services/apiService'

function App() {
  // Main application state management
  const [activeWorkflowId, setActiveWorkflowId] = useState(null)
  const [workflows, setWorkflows] = useState({}) // Map of workflow IDs to workflow info
  const [conversation, setConversation] = useState([]) // Messages for current workflow
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  // Tool confirmation state
  const [pendingConfirmation, setPendingConfirmation] = useState(false)
  const [toolConfirmationData, setToolConfirmationData] = useState(null)
  
  // Cooldown ref to prevent dialog from reappearing after user action
  const confirmationCooldownRef = useRef(null)

  // Error handling helper - defined first to avoid hoisting issues
  const handleError = useCallback((error, context = '') => {
    console.error(`Error ${context}:`, error)
    const errorMessage = error?.message || 'An unexpected error occurred'
    setError(`${context ? context + ': ' : ''}${errorMessage}`)
    
    // Clear error after 5 seconds
    setTimeout(() => setError(null), 5000)
  }, [])

  // Clear error when user interacts
  const clearError = useCallback(() => {
    setError(null)
  }, [])







  // Handle active workflow changes
  useEffect(() => {
    if (activeWorkflowId) {
      // Initialize empty conversation for new workflow
      setConversation([])
      setLoading(false)
      setPendingConfirmation(false)
      setToolConfirmationData(null)
    } else {
      // No active workflow, clear state
      setConversation([])
      setPendingConfirmation(false)
      setToolConfirmationData(null)
    }
  }, [activeWorkflowId])



  // Workflow management functions
  const handleStartWorkflow = useCallback(async (agentName, workflowId) => {
    try {
      setLoading(true)
      clearError()

      const response = await apiService.startWorkflow(agentName, workflowId)
      
      if (response.success && response.data) {
        // Add new workflow to state
        const newWorkflow = {
          id: workflowId,
          runId: response.data.workflow_run_id,
          agentName: agentName,
          status: 'active',
          createdAt: Date.now(),
          lastActivity: Date.now()
        }

        setWorkflows(prev => ({
          ...prev,
          [workflowId]: newWorkflow
        }))

        // Set as active workflow
        setActiveWorkflowId(workflowId)
      }
    } catch (error) {
      handleError(error, 'Failed to start workflow')
    } finally {
      setLoading(false)
    }
  }, [handleError, clearError])

  const handleSelectWorkflow = useCallback((workflowId) => {
    if (workflowId !== activeWorkflowId) {
      setActiveWorkflowId(workflowId)
      clearError()
    }
  }, [activeWorkflowId, clearError])

  // Chat functions
  const handleSendMessage = useCallback(async (message) => {
    if (!activeWorkflowId || !message.trim()) return

    try {
      clearError()

      // Send message to API (polling will update the conversation)
      const response = await apiService.sendPrompt(activeWorkflowId, message)
      
      if (response.success) {
        // Message sent successfully
      }
    } catch (error) {
      handleError(error, 'Failed to send message')
    }
  }, [activeWorkflowId, handleError, clearError])

  // Tool confirmation functions
  const handleConfirmTool = useCallback(async (confirmed) => {
    if (!activeWorkflowId) {
      return
    }

    // Store the current tool data before clearing state
    const currentToolData = toolConfirmationData;

    // Immediately clear the confirmation dialog to prevent UI lag and race conditions
    setPendingConfirmation(false)
    setToolConfirmationData(null)
    
    // Set cooldown to prevent polling from re-showing the dialog
    confirmationCooldownRef.current = Date.now()

    try {
      setLoading(true)
      clearError()

      if (confirmed) {
        // Check if this is a workflow completion confirmation or tool confirmation
        if (currentToolData?.type === 'completion') {
          const response = await apiService.confirmCompletion(activeWorkflowId)
          
          if (response.success) {
            // Don't update conversation here - let polling handle it
            // This prevents the "reload" effect
          }
        } else {
          const response = await apiService.confirmTool(activeWorkflowId)
          
          if (response.success) {
            // Don't update conversation here - let polling handle it
            // This prevents the "reload" effect
          }
        }
      } else {
        // Check if this is a workflow completion cancellation or tool cancellation
        if (currentToolData?.type === 'completion') {
          const response = await apiService.cancelCompletion(activeWorkflowId)
          
          if (response.success) {
            // Don't update conversation here - let polling handle it
            // This prevents the "reload" effect
          }
        } else {
          const response = await apiService.cancelTool(activeWorkflowId)
          
          if (response.success) {
            // Don't update conversation here - let polling handle it
            // This prevents the "reload" effect
          }
        }
      }

    } catch (error) {
      console.error('Error in handleConfirmTool:', error)
      handleError(error, confirmed ? 'Failed to confirm' : 'Failed to cancel')
      
      // On error, don't restore the confirmation state to avoid confusion
      // The polling will pick up the correct state on the next cycle
    } finally {
      setLoading(false)
    }
  }, [activeWorkflowId, toolConfirmationData, handleError, clearError])

  const handleToolConfirmationModal = useCallback((confirmed) => {
    handleConfirmTool(confirmed)
  }, [handleConfirmTool])

  // Poll for conversation updates
  useEffect(() => {
    if (!activeWorkflowId) return;
    
    const pollConversation = async () => {
      try {
        const response = await apiService.getConversationHistory(activeWorkflowId);
        if (response.success && response.data.messages) {
          const newMessages = response.data.messages;
          
          // Always update with the latest messages from the API
          setConversation(newMessages);
          
          // Check for pending tool confirmations using the fresh newMessages
          const messages = newMessages;
          
          // Look for any unconfirmed tool confirmation (not just the last message)
          let foundPendingConfirmation = false;
          let newToolConfirmationData = null;

          // Search backwards through messages to find the most recent tool confirmation
          for (let i = messages.length - 1; i >= 0; i--) {
            const message = messages[i];
            
            if (message?.actor === 'agent' && message?.response) {
              let messageData = message.response;
              
              // Handle string responses (parse JSON if possible)
              if (typeof messageData === 'string') {
                try {
                  messageData = JSON.parse(messageData);
                } catch {
                  messageData = { response: messageData };
                }
              }
              
              // Check if this is a tool confirmation that hasn't been confirmed yet
              if (messageData?.next === 'confirm' && messageData?.tool) {
                // Check if there's a corresponding user_confirmed_tool_run or user_cancelled_tool_run message after this
                let isAlreadyProcessed = false;
                for (let j = i + 1; j < messages.length; j++) {
                  const laterMessage = messages[j];
                  
                  // Check for confirmation
                  if (laterMessage?.actor === 'user_confirmed_tool_run' && 
                      typeof laterMessage.response === 'object' &&
                      laterMessage.response?.tool === messageData.tool &&
                      laterMessage.response?.status === 'user_confirmed') {
                    isAlreadyProcessed = true;
                    break;
                  }
                  // Check for cancellation
                  if (laterMessage?.actor === 'user_cancelled_tool_run' && 
                      typeof laterMessage.response === 'object' &&
                      laterMessage.response?.tool === messageData.tool &&
                      laterMessage.response?.status === 'user_cancelled') {
                    isAlreadyProcessed = true;
                    break;
                  }
                }
                
                if (!isAlreadyProcessed) {
                  // Found an unprocessed tool confirmation
                  foundPendingConfirmation = true;
                  
                  // Handle both direct tool confirmations and child workflow tool confirmations
                  let toolName, toolArgs, toolResponse;
                  
                  if (messageData.tool) {
                    // Direct tool confirmation (top-level fields)
                    toolName = messageData.tool;
                    toolArgs = messageData.args || {};
                    toolResponse = messageData.response || `Execute ${messageData.tool}`;
                  } else if (messageData.response && typeof messageData.response === 'object' && messageData.response.tool) {
                    // Child workflow tool confirmation (nested in response)
                    toolName = messageData.response.tool;
                    toolArgs = messageData.response.args || {};
                    toolResponse = messageData.response.response || `Execute ${messageData.response.tool}`;
                  } else {
                    // Fallback - shouldn't happen but handle gracefully
                    toolName = 'Unknown Tool';
                    toolArgs = {};
                    toolResponse = 'Execute tool';
                  }
                  
                  newToolConfirmationData = {
                    toolName: toolName,
                    parameters: toolArgs,
                    description: toolResponse,
                    impact: 'medium',
                    type: 'tool'
                  };
                  break;
                }
              }
              // Check if this is a workflow completion confirmation that hasn't been confirmed yet
              else if (messageData?.next === 'confirm_completion' && messageData?.type === 'workflow_completion') {
                // Get the agent_type for this completion to match with confirmation messages
                const completionAgentType = message.agent_type || messageData.agent_type;
                
                // Check if there's a corresponding user_confirmed_completion or user_cancelled_completion message after this
                // IMPORTANT: Match by agent_type to distinguish between different workflows' completions
                let isAlreadyProcessed = false;
                for (let j = i + 1; j < messages.length; j++) {
                  const laterMessage = messages[j];
                  
                  // Check for completion confirmation - must match agent_type
                  if (laterMessage?.actor === 'user_confirmed_completion' && 
                      typeof laterMessage.response === 'object' &&
                      laterMessage.response?.status === 'workflow_completion_confirmed') {
                    // Match by agent_type to ensure we're matching the right workflow's confirmation
                    const confirmAgentType = laterMessage.agent_type || laterMessage.response?.agent_type;
                    // If both have agent_type, they must match. If either is missing, assume it's a match
                    // (for backwards compatibility with messages that don't have agent_type)
                    if (completionAgentType && confirmAgentType) {
                      if (completionAgentType === confirmAgentType) {
                        isAlreadyProcessed = true;
                        break;
                      }
                      // Different agent_types - keep looking for a matching confirmation
                    } else {
                      // One or both missing agent_type - assume match for backwards compatibility
                      isAlreadyProcessed = true;
                      break;
                    }
                  }
                  // Check for completion cancellation - backend sends user_cancelled_tool_run for both tools and completions
                  if ((laterMessage?.actor === 'user_cancelled_completion' || laterMessage?.actor === 'user_cancelled_tool_run') && 
                      typeof laterMessage.response === 'object' &&
                      (laterMessage.response?.status === 'workflow_completion_cancelled' || 
                       laterMessage.response?.status === 'user_cancelled')) {
                    // Match by agent_type for cancellations too
                    const cancelAgentType = laterMessage.agent_type || laterMessage.response?.agent_type;
                    if (completionAgentType && cancelAgentType) {
                      if (completionAgentType === cancelAgentType) {
                        isAlreadyProcessed = true;
                        break;
                      }
                    } else {
                      isAlreadyProcessed = true;
                      break;
                    }
                  }
                }
                
                if (!isAlreadyProcessed) {
                  // Found an unprocessed workflow completion confirmation
                  foundPendingConfirmation = true;
                  
                  // Use the structured agent_result if available, otherwise empty object
                  const agentResult = messageData.agent_result || {};
                  
                  // Include agent_type to distinguish between different workflows' completions
                  const agentType = message.agent_type || messageData.agent_type || 'Workflow';
                  
                  // Use agent type in the tool name for clarity
                  const completionName = `Complete ${agentType}`;
                  
                  newToolConfirmationData = {
                    toolName: completionName,
                    parameters: agentResult,
                    description: messageData.response || 'Complete the workflow and return results',
                    impact: 'high',
                    type: 'completion',
                    agentType: agentType
                  };
                  break;
                }
              }
            }
          }
          
          // Update state atomically to prevent race conditions
          if (foundPendingConfirmation && newToolConfirmationData) {
            // Check if we're in cooldown period (3 seconds after user action)
            const cooldownActive = confirmationCooldownRef.current && 
              (Date.now() - confirmationCooldownRef.current) < 3000;
            
            if (!cooldownActive) {
              // Only update if the tool or agent has changed to prevent unnecessary re-renders
              // Include agentType in comparison to distinguish between different workflows' completions
              setToolConfirmationData(prevData => {
                const toolChanged = prevData?.toolName !== newToolConfirmationData.toolName;
                const agentChanged = prevData?.agentType !== newToolConfirmationData.agentType;
                if (toolChanged || agentChanged) {
                  setPendingConfirmation(true);
                  return newToolConfirmationData;
                }
                return prevData;
              });
            }
          } else {
            // No pending confirmation found, clear the state and reset cooldown
            setPendingConfirmation(false);
            setToolConfirmationData(null);
            confirmationCooldownRef.current = null;
          }
        }
      } catch (error) {
        // If workflow not found (404), stop polling by clearing the active workflow
        if (error.status === 404) {
          setActiveWorkflowId(null);
          handleError(error, 'Workflow not found - it may have completed or been terminated');
        } else if (error.status === 504) {
          // 504 Gateway Timeout is normal when workflow is processing - just retry on next poll
          // Don't log these to avoid console spam
        } else {
          console.error('Error polling conversation:', error);
        }
      }
    };
    
    // Poll immediately, then every 1 second
    pollConversation();
    const pollInterval = setInterval(pollConversation, 1000);
    
    return () => clearInterval(pollInterval);
  }, [activeWorkflowId, handleError]);

  // Auto-start workflow on app load
  useEffect(() => {
    const autoStartWorkflow = async () => {
      if (Object.keys(workflows).length === 0 && !activeWorkflowId) {
        const randomId = `workflow-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
        await handleStartWorkflow('Supervisor Agent', randomId)
      }
    }
    
    // Small delay to ensure everything is initialized
    const timer = setTimeout(autoStartWorkflow, 1000)
    return () => clearTimeout(timer)
  }, [workflows, activeWorkflowId, handleStartWorkflow])

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-content" style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem'}}>
          <div className="logo" style={{display: 'flex', alignItems: 'center', gap: '0.75rem'}}>
            <div className="logo-icon" aria-hidden style={{width: '40px', height: '40px', background: 'linear-gradient(90deg,#60a5fa,#7c3aed)', borderRadius: '8px'}}></div>
            <div>
              <h1 style={{fontSize: '1.125rem', fontWeight: 700, color: '#1f2937'}}>Supervisor Agent</h1>
              <div style={{fontSize: '0.8rem', color: '#718096'}}>Agent Interface</div>
            </div>
          </div>

          {activeWorkflowId && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(72, 187, 120, 0.08)', padding: '0.4rem 0.8rem', borderRadius: '9999px', border: '1px solid rgba(72, 187, 120, 0.18)'}}>
              <div style={{width: '8px', height: '8px', background: '#48bb78', borderRadius: '50%'}}></div>
              <span style={{ fontSize: '0.9rem', color: '#2f855a', fontWeight: 600 }}>{activeWorkflowId}</span>
            </div>
          )}
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div style={{
          background: 'linear-gradient(135deg, #fed7d7, #feb2b2)',
          border: '2px solid #f56565',
          borderRadius: '0.5rem',
          padding: '1rem 2rem',
          margin: '1rem 2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 4px 20px rgba(245, 101, 101, 0.2)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.2rem' }}>⚠️</span>
            <p style={{ color: '#c53030', fontWeight: '600' }}>{error}</p>
          </div>
          <button
            onClick={clearError}
            style={{
              background: 'none',
              border: 'none',
              color: '#e53e3e',
              cursor: 'pointer',
              padding: '0.5rem',
              borderRadius: '0.25rem',
              fontSize: '1.2rem'
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content */}
      <main className="main-content">
        {/* Welcome Section */}
        {!activeWorkflowId && Object.keys(workflows).length === 0 && (
          <div className="welcome-section">
            <div className="welcome-icon">🤖</div>
            <h2 className="welcome-title">
              Welcome to Temporal Workflows
            </h2>
            <p className="welcome-description">
              Create and manage AI agent workflows with real-time conversation capabilities. 
              Start by creating your first workflow below.
            </p>
          </div>
        )}

        {/* Chat Window */}
        <div className="chat-container">
          <ModernChatWindow
            messages={conversation}
            onSendMessage={handleSendMessage}
            loading={loading}
            activeWorkflowId={activeWorkflowId}
            onConfirmTool={handleToolConfirmationModal}
            pendingConfirmation={pendingConfirmation}
            toolConfirmationData={toolConfirmationData}
            />
        </div>
      </main>


    </div>
  )
}

export default App
