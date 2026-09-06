import { fetchApi } from './apiClient';

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001';

/**
 * Fetch all registered tools with descriptions, permissions, and input schemas.
 */
export async function listTools() {
  return fetchApi('/api/v1/tools');
}

/**
 * Manually execute a tool from the tester playground.
 */
export async function executeTool(toolName, args = {}, { userId = DEFAULT_USER_ID, projectId = null, threadId = null } = {}) {
  return fetchApi('/api/v1/tools/execute', {
    method: 'POST',
    body: JSON.stringify({
      tool_name: toolName,
      arguments: args,
      parameters: args,
      user_id: userId,
      project_id: projectId,
      thread_id: threadId,
    }),
  });
}
