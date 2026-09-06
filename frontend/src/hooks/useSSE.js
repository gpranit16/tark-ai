import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../api/apiClient';

export function useSSE() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const abortControllerRef = useRef(null);

  const streamChat = useCallback(async (threadId, payload, callbacks) => {
    const {
      onMessageStart,
      onTextDelta,
      onMessageComplete,
      onError,
      // Phase 7 RAG callbacks (optional)
      onRetrievalStarted,
      onRetrievalComplete,
      onRerankingStarted,
      onRerankingComplete,
      onGrading,
      onQueryRewrite,
      onCragRetry,
      onRagGenerating,
      onCitation,
      onRagStage,
      // Phase 9 Tool callbacks (optional)
      onToolAvailable,
      onToolStarted,
      onToolResult,
      onToolError,
      // Phase 10 Deep Research callbacks (optional)
      onResearchStarted,
      onResearchPlanning,
      onResearchPlanCreated,
      onResearchTaskStarted,
      onResearchTaskProgress,
      onResearchTaskCompleted,
      onResearchTaskFailed,
      onResearchEvidenceCollected,
      onResearchVerificationStarted,
      onResearchVerificationComplete,
      onResearchRetry,
      onResearchSynthesisStarted,
      onResearchCitation,
      onResearchComplete,
      onResearchCancelled,
      onResearchError,
      // Phase 12 Coding callbacks (optional)
      onCodingStarted,
      onCodingFile,
      onCodingContextReady,
      onCodingGeneration,
      onCodingComplete,
      onCodingError,
      // GPT-Style Memory callbacks (optional)
      onMemorySaved,
      onMemoryForgotten,
    } = callbacks;


    setIsStreaming(true);
    setError(null);

    abortControllerRef.current = new AbortController();

    try {
      const token = localStorage.getItem('tarkai_access_token');
      const response = await fetch(`${API_BASE_URL}/api/v1/threads/${threadId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status}`;
        try {
          const errData = await response.json();
          errorDetail = errData.detail || JSON.stringify(errData);
        } catch (_) {}
        throw new Error(errorDetail);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = 'message';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const dataStr = line.slice(5).trim();
            if (!dataStr || dataStr === '[DONE]') continue;
            try {
              const data = JSON.parse(dataStr);
              // Standard events
              if (currentEvent === 'message_start' && onMessageStart) onMessageStart(data);
              else if (currentEvent === 'text_delta' && onTextDelta) onTextDelta(data);
              else if (currentEvent === 'message_complete' && onMessageComplete) onMessageComplete(data);
              else if (currentEvent === 'error' && onError) onError(new Error(data.detail || data.message || 'Stream error'));
              // Phase 7 RAG events
              else if (currentEvent === 'retrieval_started' && onRetrievalStarted) onRetrievalStarted(data);
              else if (currentEvent === 'retrieval_complete' && onRetrievalComplete) onRetrievalComplete(data);
              else if (currentEvent === 'reranking_started' && onRerankingStarted) onRerankingStarted(data);
              else if (currentEvent === 'reranking_complete' && onRerankingComplete) onRerankingComplete(data);
              else if (currentEvent === 'grading' && onGrading) onGrading(data);
              else if (currentEvent === 'query_rewrite' && onQueryRewrite) onQueryRewrite(data);
              else if (currentEvent === 'crag_retry' && onCragRetry) onCragRetry(data);
              else if (currentEvent === 'rag_generating' && onRagGenerating) onRagGenerating(data);
              else if (currentEvent === 'citation' && onCitation) onCitation(data);
              else if (currentEvent === 'rag_stage' && onRagStage) onRagStage(data);
              // Phase 9 Tool events
              else if (currentEvent === 'tool_available' && onToolAvailable) onToolAvailable(data);
              else if (currentEvent === 'tool_started' && onToolStarted) onToolStarted(data);
              else if (currentEvent === 'tool_result' && onToolResult) onToolResult(data);
              else if (currentEvent === 'tool_error' && onToolError) onToolError(data);
              // Phase 10 Deep Research events
              else if (currentEvent === 'research_started' && onResearchStarted) onResearchStarted(data);
              else if (currentEvent === 'research_planning' && onResearchPlanning) onResearchPlanning(data);
              else if (currentEvent === 'research_plan_created' && onResearchPlanCreated) onResearchPlanCreated(data);
              else if (currentEvent === 'research_task_started' && onResearchTaskStarted) onResearchTaskStarted(data);
              else if (currentEvent === 'research_task_progress' && onResearchTaskProgress) onResearchTaskProgress(data);
              else if (currentEvent === 'research_task_completed' && onResearchTaskCompleted) onResearchTaskCompleted(data);
              else if (currentEvent === 'research_task_failed' && onResearchTaskFailed) onResearchTaskFailed(data);
              else if (currentEvent === 'research_evidence_collected' && onResearchEvidenceCollected) onResearchEvidenceCollected(data);
              else if (currentEvent === 'research_verification_started' && onResearchVerificationStarted) onResearchVerificationStarted(data);
              else if (currentEvent === 'research_verification_complete' && onResearchVerificationComplete) onResearchVerificationComplete(data);
              else if (currentEvent === 'research_retry' && onResearchRetry) onResearchRetry(data);
              else if (currentEvent === 'research_synthesis_started' && onResearchSynthesisStarted) onResearchSynthesisStarted(data);
              else if (currentEvent === 'research_citation' && onResearchCitation) onResearchCitation(data);
              else if (currentEvent === 'research_complete' && onResearchComplete) onResearchComplete(data);
              else if (currentEvent === 'research_cancelled' && onResearchCancelled) onResearchCancelled(data);
              else if (currentEvent === 'research_error' && onResearchError) onResearchError(data);
              // Phase 12 Coding events
              else if (currentEvent === 'coding_started' && onCodingStarted) onCodingStarted(data);
              else if (currentEvent === 'coding_file' && onCodingFile) onCodingFile(data);
              else if (currentEvent === 'coding_context_ready' && onCodingContextReady) onCodingContextReady(data);
              else if (currentEvent === 'coding_generation' && onCodingGeneration) onCodingGeneration(data);
              else if (currentEvent === 'coding_complete' && onCodingComplete) onCodingComplete(data);
              else if (currentEvent === 'coding_error' && onCodingError) onCodingError(data);
              // GPT-Style Memory events
              else if (currentEvent === 'memory_saved' && onMemorySaved) onMemorySaved(data);
              else if (currentEvent === 'memory_forgotten' && onMemoryForgotten) onMemoryForgotten(data);

            } catch (e) {
              console.warn('[SSE] Failed to parse data:', dataStr, e);
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('[SSE] Stream aborted by user');
      } else {
        console.error('[SSE] Error:', err);
        setError(err.message);
        if (callbacks.onError) callbacks.onError(err);
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  }, []);

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  return { streamChat, stopStreaming, isStreaming, error };
}
