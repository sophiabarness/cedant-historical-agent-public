// API service for making HTTP requests
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Custom error class for API-related errors
 */
class ApiError extends Error {
  constructor(message, status, response = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.response = response;
  }

  static fromResponse(response, data = null) {
    const message = data?.message || `HTTP ${response.status}: ${response.statusText}`;
    return new ApiError(message, response.status, data);
  }
}

/**
 * API service class with comprehensive error handling and response validation
 */
class ApiService {
  constructor() {
    this.baseURL = API_BASE_URL;
  }

  /**
   * Validates API response structure
   * @param {Object} data - Response data to validate
   * @returns {Object} Validated response data
   * @throws {ApiError} If response structure is invalid
   */
  validateResponse(data) {
    if (!data || typeof data !== 'object') {
      throw new ApiError('Invalid response format: expected object', 0);
    }

    // Check for standard API response structure
    if (!Object.prototype.hasOwnProperty.call(data, 'success')) {
      throw new ApiError('Invalid response format: missing success field', 0);
    }

    if (!data.success && !data.message) {
      throw new ApiError('Invalid error response: missing error message', 0);
    }

    return data;
  }

  /**
   * Parse error response and extract meaningful error message
   * @param {Response} response - Fetch response object
   * @param {Object} data - Parsed response data
   * @returns {ApiError} Formatted API error
   */
  parseError(response, data = null) {
    if (data && data.message) {
      return new ApiError(data.message, response.status, data);
    }

    // Default error messages based on status codes
    const defaultMessages = {
      400: 'Bad Request: Invalid input data',
      401: 'Unauthorized: Authentication required',
      403: 'Forbidden: Access denied',
      404: 'Not Found: Resource not found',
      409: 'Conflict: Resource already exists',
      422: 'Unprocessable Entity: Validation failed',
      500: 'Internal Server Error: Server encountered an error',
      502: 'Bad Gateway: Server is temporarily unavailable',
      503: 'Service Unavailable: Server is temporarily unavailable'
    };

    const message = defaultMessages[response.status] || `HTTP ${response.status}: ${response.statusText}`;
    return new ApiError(message, response.status, data);
  }

  /**
   * Base request method with comprehensive error handling
   * @param {string} endpoint - API endpoint path
   * @param {Object} options - Fetch options
   * @returns {Promise<Object>} API response data
   * @throws {ApiError} For API-related errors
   */
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      let data = null;

      // Try to parse JSON response
      try {
        data = await response.json();
      } catch {
        if (!response.ok) {
          throw this.parseError(response);
        }
        throw new ApiError('Invalid JSON response from server', response.status);
      }

      // Handle non-2xx responses
      if (!response.ok) {
        throw this.parseError(response, data);
      }

      // Validate and return successful response
      return this.validateResponse(data);

    } catch (error) {
      // Re-throw ApiError instances
      if (error instanceof ApiError) {
        throw error;
      }

      // Handle network errors and other fetch failures
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        throw new ApiError('Network error: Unable to connect to server', 0);
      }

      // Handle timeout errors
      if (error.name === 'AbortError') {
        throw new ApiError('Request timeout: Server did not respond in time', 0);
      }

      // Wrap other errors
      throw new ApiError(`Request failed: ${error.message}`, 0);
    }
  }

  /**
   * GET request wrapper
   * @param {string} endpoint - API endpoint path
   * @returns {Promise<Object>} API response data
   */
  async get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  }

  /**
   * POST request wrapper
   * @param {string} endpoint - API endpoint path
   * @param {Object} data - Request body data
   * @returns {Promise<Object>} API response data
   */
  async post(endpoint, data) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Workflow Management API Methods

  /**
   * Start a new workflow with specified agent and workflow ID
   * @param {string} agentName - Name of the agent to use
   * @param {string} workflowId - Unique identifier for the workflow
   * @returns {Promise<Object>} Workflow creation response
   * @throws {ApiError} If workflow creation fails
   */
  async startWorkflow(agentName, workflowId) {
    if (!agentName || typeof agentName !== 'string') {
      throw new ApiError('Agent name is required and must be a string', 400);
    }

    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.post('/start-workflow', {
      agent_name: agentName,
      workflow_id: workflowId
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id || !response.data.workflow_run_id) {
      throw new ApiError('Invalid workflow creation response: missing required fields', 0);
    }

    return response;
  }

  /**
   * Send a prompt message to an active workflow
   * @param {string} workflowId - ID of the target workflow
   * @param {string} prompt - Message to send to the workflow
   * @returns {Promise<Object>} Prompt sending response
   * @throws {ApiError} If prompt sending fails
   */
  async sendPrompt(workflowId, prompt) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    if (!prompt || typeof prompt !== 'string') {
      throw new ApiError('Prompt is required and must be a string', 400);
    }

    const response = await this.post('/send-prompt', {
      workflow_id: workflowId,
      prompt: prompt
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id) {
      throw new ApiError('Invalid prompt response: missing workflow_id', 0);
    }

    return response;
  }

  /**
   * Confirm tool execution for a workflow
   * @param {string} workflowId - ID of the workflow requesting confirmation
   * @returns {Promise<Object>} Confirmation response
   * @throws {ApiError} If confirmation fails
   */
  async confirmTool(workflowId) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.post('/confirm-tool', {
      workflow_id: workflowId
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id) {
      throw new ApiError('Invalid confirmation response: missing workflow_id', 0);
    }

    return response;
  }

  /**
   * Cancel tool execution for a workflow
   * @param {string} workflowId - ID of the workflow to cancel tool execution
   * @returns {Promise<Object>} Cancellation response
   * @throws {ApiError} If cancellation fails
   */
  async cancelTool(workflowId) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.post('/cancel-tool', {
      workflow_id: workflowId
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id) {
      throw new ApiError('Invalid cancellation response: missing workflow_id', 0);
    }

    return response;
  }

  /**
   * Confirm workflow completion for a workflow
   * @param {string} workflowId - ID of the workflow requesting completion confirmation
   * @returns {Promise<Object>} Completion confirmation response
   * @throws {ApiError} If completion confirmation fails
   */
  async confirmCompletion(workflowId) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.post('/confirm-completion', {
      workflow_id: workflowId
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id) {
      throw new ApiError('Invalid completion confirmation response: missing workflow_id', 0);
    }

    return response;
  }

  /**
   * Cancel workflow completion for a workflow
   * @param {string} workflowId - ID of the workflow to cancel completion
   * @returns {Promise<Object>} Completion cancellation response
   * @throws {ApiError} If completion cancellation fails
   */
  async cancelCompletion(workflowId) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.post('/cancel-completion', {
      workflow_id: workflowId
    });

    // Validate expected response structure
    if (!response.data || !response.data.workflow_id) {
      throw new ApiError('Invalid completion cancellation response: missing workflow_id', 0);
    }

    return response;
  }

  // Conversation API Methods with Smart Polling

  /**
   * Get conversation history for a specific workflow
   * @param {string} workflowId - ID of the workflow
   * @returns {Promise<Object>} Conversation history response
   * @throws {ApiError} If fetching conversation fails
   */
  async getConversationHistory(workflowId) {
    if (!workflowId || typeof workflowId !== 'string') {
      throw new ApiError('Workflow ID is required and must be a string', 400);
    }

    const response = await this.get(`/get-conversation-history/${workflowId}`);

    // Validate expected response structure - backend returns conversation_history object
    if (!response.data || !response.data.conversation_history) {
      throw new ApiError('Invalid conversation response: missing conversation_history', 0);
    }

    // Transform backend format to frontend format
    const messages = response.data.conversation_history.messages || [];
    return {
      ...response,
      data: {
        messages: messages
      }
    };
  }
}

/**
 * Smart polling manager for conversation updates
 */
class ConversationPoller {
  constructor(apiService) {
    this.apiService = apiService;
    this.pollingIntervals = new Map(); // workflowId -> interval info
    this.callbacks = new Map(); // workflowId -> callback function
    this.isPolling = new Map(); // workflowId -> boolean
  }

  /**
   * Start polling for a specific workflow
   * @param {string} workflowId - Workflow to poll
   * @param {Function} callback - Function to call with updates
   * @param {Object} options - Polling configuration
   */
  startPolling(workflowId, callback, options = {}) {
    const config = {
      initialInterval: options.initialInterval || 2000, // 2 seconds
      maxInterval: options.maxInterval || 10000, // 10 seconds
      backoffMultiplier: options.backoffMultiplier || 1.5,
      ...options
    };

    // Stop existing polling for this workflow
    this.stopPolling(workflowId);

    this.callbacks.set(workflowId, callback);
    this.isPolling.set(workflowId, true);
    
    const intervalInfo = {
      current: config.initialInterval,
      max: config.maxInterval,
      multiplier: config.backoffMultiplier,
      timeoutId: null,
      lastActivity: Date.now()
    };

    this.pollingIntervals.set(workflowId, intervalInfo);
    this._scheduleNextPoll(workflowId);
  }

  /**
   * Stop polling for a specific workflow
   * @param {string} workflowId - Workflow to stop polling
   */
  stopPolling(workflowId) {
    const intervalInfo = this.pollingIntervals.get(workflowId);
    if (intervalInfo && intervalInfo.timeoutId) {
      clearTimeout(intervalInfo.timeoutId);
    }

    this.pollingIntervals.delete(workflowId);
    this.callbacks.delete(workflowId);
    this.isPolling.set(workflowId, false);
  }

  /**
   * Pause polling for a workflow (can be resumed)
   * @param {string} workflowId - Workflow to pause
   */
  pausePolling(workflowId) {
    const intervalInfo = this.pollingIntervals.get(workflowId);
    if (intervalInfo && intervalInfo.timeoutId) {
      clearTimeout(intervalInfo.timeoutId);
      intervalInfo.timeoutId = null;
    }
    this.isPolling.set(workflowId, false);
  }

  /**
   * Resume polling for a workflow
   * @param {string} workflowId - Workflow to resume
   */
  resumePolling(workflowId) {
    if (this.pollingIntervals.has(workflowId)) {
      this.isPolling.set(workflowId, true);
      this._scheduleNextPoll(workflowId);
    }
  }

  /**
   * Reset polling interval to initial value (call after user activity)
   * @param {string} workflowId - Workflow to reset
   */
  resetInterval(workflowId) {
    const intervalInfo = this.pollingIntervals.get(workflowId);
    if (intervalInfo) {
      intervalInfo.current = 2000; // Reset to initial 2 seconds
      intervalInfo.lastActivity = Date.now();
    }
  }

  /**
   * Check if currently polling a workflow
   * @param {string} workflowId - Workflow to check
   * @returns {boolean} True if actively polling
   */
  isActivelyPolling(workflowId) {
    return this.isPolling.get(workflowId) === true;
  }

  /**
   * Stop all polling activities
   */
  stopAll() {
    for (const workflowId of this.pollingIntervals.keys()) {
      this.stopPolling(workflowId);
    }
  }

  /**
   * Schedule the next poll for a workflow
   * @private
   */
  _scheduleNextPoll(workflowId) {
    const intervalInfo = this.pollingIntervals.get(workflowId);
    const callback = this.callbacks.get(workflowId);

    if (!intervalInfo || !callback || !this.isPolling.get(workflowId)) {
      return;
    }

    intervalInfo.timeoutId = setTimeout(async () => {
      try {
        // Fetch conversation history
        const response = await this.apiService.getConversationHistory(workflowId);
        
        // Call the callback with the response
        callback(response, null);

        // Check if there was recent activity to adjust interval
        const timeSinceActivity = Date.now() - intervalInfo.lastActivity;
        if (timeSinceActivity > 30000) { // 30 seconds of inactivity
          // Increase interval with exponential backoff
          intervalInfo.current = Math.min(
            intervalInfo.current * intervalInfo.multiplier,
            intervalInfo.max
          );
        }

        // Schedule next poll if still active
        if (this.isPolling.get(workflowId)) {
          this._scheduleNextPoll(workflowId);
        }

      } catch (error) {
        // Call callback with error
        callback(null, error);

        // Continue polling even on errors, but with longer interval
        intervalInfo.current = Math.min(intervalInfo.current * 2, intervalInfo.max);
        
        if (this.isPolling.get(workflowId)) {
          this._scheduleNextPoll(workflowId);
        }
      }
    }, intervalInfo.current);
  }
}

// Create and export poller instance
const conversationPoller = new ConversationPoller(new ApiService());

export { ConversationPoller, conversationPoller };

// Export both the class and a default instance
export { ApiError };
export default new ApiService();