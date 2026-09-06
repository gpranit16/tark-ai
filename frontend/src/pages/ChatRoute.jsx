import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useAppStore } from '../stores/useAppStore';
import { useAuthStore } from '../stores/useAuthStore';
import { threadApi } from '../api/threadApi';
import { fileApi } from '../api/fileApi';
import { settingsApi } from '../api/settingsApi';
import { useSSE } from '../hooks/useSSE';
import { Send, Square, Globe, EyeOff, ShieldAlert, Sparkles, Code2, Brain, Loader2, FileText, BookOpen, Database, Image as ImageIcon, HardDrive, Cloud } from 'lucide-react';
import clsx from 'clsx';
import 'highlight.js/styles/atom-one-dark.css';
import FileUploader from '../components/chat/FileUploader';
import FileList from '../components/chat/FileList';
import ResearchProgress from '../components/chat/ResearchProgress';
import ResearchCitations from '../components/chat/ResearchCitations';
import CodeBlock from '../components/chat/CodeBlock';
import CodingProgress from '../components/chat/CodingProgress';
import CRAGDebugPanel from '../components/chat/CRAGDebugPanel';
import TarkAmbientBackground from '../components/TarkAmbientBackground';
import SplineRobot from '../components/SplineRobot';
import TarkAssistantAvatar from '../components/chat/TarkAssistantAvatar';
import ModeModelSelector from '../components/chat/ModeModelSelector';

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001';

export default function ChatRoute() {
  const { threadId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const toggleContextPanel = useAppStore((s) => s.toggleContextPanel);
  const mode = useAppStore((s) => s.mode);
  const model = useAppStore((s) => s.model);
  const provider = useAppStore((s) => s.provider);
  const setMode = useAppStore((s) => s.setMode);
  const setModel = useAppStore((s) => s.setModel);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const activeProject = useAppStore((s) => s.activeProject);
  const setActiveThreadId = useAppStore((s) => s.setActiveThreadId);
  const setUserSettingsStore = useAppStore((s) => s.setUserSettings);
  const enterToSend = useAppStore((s) => s.enterToSend);
  const showCitationsSetting = useAppStore((s) => s.showCitations);
  const showTimestamps = useAppStore((s) => s.showTimestamps);
  const autoScrollSetting = useAppStore((s) => s.autoScroll);
  const compactMessages = useAppStore((s) => s.compactMessages);
  const showAttachmentPreviews = useAppStore((s) => s.showAttachmentPreviews);
  const chatDensity = useAppStore((s) => s.chatDensity);

  const { data: userSettingsEnvelope } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.getSettings(DEV_USER_ID),
    enabled: !!isAuthenticated,
  });

  useEffect(() => {
    if (userSettingsEnvelope?.settings) {
      setUserSettingsStore(userSettingsEnvelope.settings);
    }
  }, [userSettingsEnvelope, setUserSettingsStore]);

  useEffect(() => {
    if (!threadId && userSettingsEnvelope?.settings?.default_mode) {
      setMode(userSettingsEnvelope.settings.default_mode);
    }
  }, [threadId, userSettingsEnvelope?.settings?.default_mode, setMode]);

  useEffect(() => {
    setActiveThreadId(threadId || null);
  }, [threadId, setActiveThreadId]);

  const [inputMessage, setInputMessage] = useState('');

  // Restore preserved draft prompt after login if present
  useEffect(() => {
    const savedDraft = sessionStorage.getItem('tarkai_pending_prompt') || location.state?.draftMessage;
    if (savedDraft) {
      setInputMessage(savedDraft);
      sessionStorage.removeItem('tarkai_pending_prompt');
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.style.height = 'auto';
          textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 256) + 'px';
        }
      }, 50);
    }
  }, [location.state]);
  const [localMessages, setLocalMessages] = useState([]);
  const [isTemporaryChat, setIsTemporaryChat] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const streamingContentRef = useRef('');
  const [streamingDisplay, setStreamingDisplay] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);
  const [pasteError, setPasteError] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [chatStorageProvider, setChatStorageProvider] = useState(() => {
    return localStorage.getItem('tarkai_chat_storage_provider') || 'local';
  });

  const toggleChatStorageProvider = () => {
    setChatStorageProvider((prev) => {
      const next = prev === 'local' ? 'b2' : 'local';
      localStorage.setItem('tarkai_chat_storage_provider', next);
      return next;
    });
  };
  // Phase 10 Deep Research state
  const [researchEvents, setResearchEvents] = useState([]);
  const [researchCitations, setResearchCitations] = useState([]);
  const [isResearching, setIsResearching] = useState(false);
  // Phase 12 Coding state
  const [codingEvents, setCodingEvents] = useState([]);
  const [isCoding, setIsCoding] = useState(false);
  const [ragMeta, setRagMeta] = useState(null); // {retrieved, reranked, confidence, attempts, decision}
  const [activeToolEvents, setActiveToolEvents] = useState([]);
  const [memoryToast, setMemoryToast] = useState(null);
  const pendingCitationsRef = useRef([]);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const prevThreadIdRef = useRef(undefined);

  const { streamChat, stopStreaming, isStreaming, error: streamError } = useSSE();

  const handleUploadSuccess = (file) => {
    setUploadedFiles(prev => [...prev, file]);
  };

  const handleRemoveFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
  };

  // Clipboard Paste Handler (Ctrl+V)
  const handlePaste = async (e) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    // 1. Detect image from clipboard items
    let imageBlob = null;
    const items = clipboardData.items || [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type && item.type.startsWith('image/')) {
        const blob = item.getAsFile();
        if (blob) {
          imageBlob = blob;
          break;
        }
      }
    }

    // Fallback to clipboard files
    if (!imageBlob && clipboardData.files?.length > 0) {
      for (let i = 0; i < clipboardData.files.length; i++) {
        const f = clipboardData.files[i];
        if (f.type && f.type.startsWith('image/')) {
          imageBlob = f;
          break;
        }
      }
    }

    // 2. If image is found, attach it via existing upload pipeline
    if (imageBlob) {
      e.preventDefault();

      let ext = '.png';
      if (imageBlob.type === 'image/jpeg') ext = '.jpg';
      else if (imageBlob.type === 'image/webp') ext = '.webp';
      else if (imageBlob.type === 'image/gif') ext = '.gif';

      const safeName =
        imageBlob.name && imageBlob.name !== 'image.png' && imageBlob.name !== 'blob' && imageBlob.name.trim() !== ''
          ? imageBlob.name
          : `screenshot-${Date.now()}${ext}`;

      const fileToUpload = new File([imageBlob], safeName, {
        type: imageBlob.type || 'image/png',
      });

      if (fileToUpload.size > 20 * 1024 * 1024) {
        setPasteError('Image is too large. Please paste a smaller image.');
        setTimeout(() => setPasteError(null), 4000);
        return;
      }

      setIsUploadingAttachment(true);
      setPasteError(null);
      try {
        const uploadedFile = await fileApi.uploadFile(fileToUpload, user?.id || DEV_USER_ID, activeProjectId || null, chatStorageProvider);
        setUploadedFiles((prev) => [...prev, uploadedFile]);
      } catch (err) {
        console.error('[ChatRoute] Clipboard upload failed:', err);
        setPasteError(err.message || 'Failed to upload pasted image');
        setTimeout(() => setPasteError(null), 4000);
      } finally {
        setIsUploadingAttachment(false);
      }
      return;
    }

    // 3. Normal text paste: do NOT preventDefault, let textarea paste naturally!
  };

  // Drag & Drop Handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer?.files || []);
    if (droppedFiles.length === 0) return;

    setIsUploadingAttachment(true);
    setPasteError(null);

    for (const f of droppedFiles) {
      try {
        const uploaded = await fileApi.uploadFile(f, user?.id || DEV_USER_ID, activeProjectId || null, chatStorageProvider);
        setUploadedFiles((prev) => [...prev, uploaded]);
      } catch (err) {
        console.error('[ChatRoute] Drop upload failed:', err);
        setPasteError(err.message || `Failed to upload ${f.name}`);
        setTimeout(() => setPasteError(null), 4000);
      }
    }
    setIsUploadingAttachment(false);
  };

  // Load server state for the active thread
  const { data: threadData, isLoading: threadLoading, isError: isThreadError, error: threadError } = useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => threadApi.getThread(threadId),
    enabled: !!threadId,
    retry: (failureCount, error) => {
      if (error?.message?.includes('404')) return false;
      return failureCount < 1;
    }
  });

  const { data: serverMessages, isLoading: messagesLoading, isError: isMessagesError, error: messagesError } = useQuery({
    queryKey: ['messages', threadId],
    queryFn: () => threadApi.getMessages(threadId),
    enabled: !!threadId,
    staleTime: 0,
    retry: (failureCount, error) => {
      if (error?.message?.includes('404')) return false;
      return failureCount < 1;
    }
  });

  // Handle 404s by clearing state and redirecting to a fresh chat
  useEffect(() => {
    const threadIs404 = isThreadError && threadError?.message?.includes('404');
    const msgsAre404 = isMessagesError && messagesError?.message?.includes('404');
    
    if (threadIs404 || msgsAre404) {
      console.warn('Thread not found, redirecting to new chat');
      setLocalMessages([]);
      setStreamingDisplay(null);
      streamingContentRef.current = '';
      navigate('/', { replace: true });
    }
  }, [isThreadError, threadError, isMessagesError, messagesError, navigate]);

  // Sync server messages — but don't overwrite while actively streaming
  useEffect(() => {
    if (serverMessages && !isStreaming) {
      setLocalMessages(serverMessages);
    }
  }, [serverMessages, isStreaming]);

  // Clear state only when genuinely switching to a DIFFERENT thread
  useEffect(() => {
    if (prevThreadIdRef.current !== undefined && prevThreadIdRef.current !== threadId) {
      setLocalMessages([]);
      setStreamingDisplay(null);
      streamingContentRef.current = '';
      setActiveToolEvents([]);
    }
    prevThreadIdRef.current = threadId;
  }, [threadId]);

  // Auto-scroll
  useEffect(() => {
    if (autoScrollSetting) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [localMessages, streamingDisplay, activeToolEvents, autoScrollSetting]);

  const handleInput = (e) => {
    setInputMessage(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 256) + 'px';
  };

  const handleKeyDown = (e) => {
    if (enterToSend) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(inputMessage);
      }
    } else {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        sendMessage(inputMessage);
      }
    }
  };

  const sendMessage = useCallback(async (text) => {
    const trimmed = (typeof text === 'string' ? text : '').trim();
    if ((!trimmed && uploadedFiles.length === 0) || isStreaming) return;

    const messageText = trimmed || (uploadedFiles.length > 0 ? `Please summarize ${uploadedFiles.map(f => f.original_filename).join(', ')}` : '');

    // Unauthenticated entry protection: smoothly preserve draft and prompt login
    if (!isAuthenticated) {
      sessionStorage.setItem('tarkai_pending_prompt', messageText);
      navigate('/login', { state: { from: location.pathname || '/', draftMessage: messageText } });
      return;
    }

    // Capture attached files BEFORE clearing state
    const filesToSend = [...uploadedFiles];
    const fileIds = filesToSend.map((f) => f.id);

    setInputMessage('');
    setUploadedFiles([]);
    setActiveToolEvents([]);
    setResearchEvents([]);
    setResearchCitations([]);
    setIsResearching(mode === 'deep_research');
    setCodingEvents([]);
    setIsCoding(mode === 'coding');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    let activeThreadId = threadId;
    let isNewThread = false;

    if (!activeThreadId) {
      try {
        const newThread = await threadApi.createThread({
          title: messageText.substring(0, 60),
          user_id: user?.id || DEV_USER_ID,
          project_id: activeProjectId || undefined,
        });
        activeThreadId = newThread.id;
        isNewThread = true;
        queryClient.invalidateQueries({ queryKey: ['threads'] });
      } catch (err) {
        console.error('[ChatRoute] Failed to create thread:', err);
        return;
      }
    } else if (!threadData?.title || threadData.title === 'New Conversation' || threadData.title === 'Untitled') {
      try {
        const titleSnippet = messageText.substring(0, 60);
        threadApi.updateThread(activeThreadId, { title: titleSnippet }).then(() => {
          queryClient.invalidateQueries({ queryKey: ['threads'] });
          queryClient.invalidateQueries({ queryKey: ['thread', activeThreadId] });
        }).catch((err) => console.warn('Could not update thread title:', err));
      } catch (e) {
        // ignore
      }
    }

    // Prepend web-search instruction if toggle is on
    const rawText = messageText;   // original text for optimistic UI display
    const finalMessage = webSearchEnabled
      ? `[Web Search Enabled] Please search the web for the latest information about: ${messageText}`
      : messageText;

    // Optimistically show user message
    setLocalMessages((prev) => [
      ...prev,
      {
        id: `opt-${Date.now()}`,
        role: 'user',
        content: rawText,   // show original text in UI (without the prefix)
        created_at: new Date().toISOString(),
        attachments: filesToSend.map((f) => ({
          file_id: f.id,
          filename: f.original_filename,
          mime_type: f.mime_type,
          size_bytes: f.size_bytes,
          extension: f.extension,
        })),
      },
    ]);

    // Start streaming UI
    streamingContentRef.current = '';
    setStreamingDisplay('');

    const payload = {
      content: finalMessage,
      provider,
      model,
      mode,
      user_id: user?.id || DEV_USER_ID,
      is_temporary: isTemporaryChat,
      ...(fileIds.length > 0 ? { file_ids: fileIds } : {}),
    };

    pendingCitationsRef.current = [];

    await streamChat(activeThreadId, payload, {
      onMessageStart: () => {
        streamingContentRef.current = '';
        setStreamingDisplay('');
      },
      onTextDelta: (data) => {
        streamingContentRef.current += data.delta ?? '';
        setStreamingDisplay(streamingContentRef.current);
      },
      onMessageComplete: (data) => {
        const finalContent = streamingContentRef.current;
        const citations = pendingCitationsRef.current || [];
        // Update RAG metadata from message_complete event if available
        let currentRagMeta = null;
        if (data && (data.crag || data.retrieval || data.latency)) {
          currentRagMeta = {
            retrieved: data.retrieval?.retrieved ?? 0,
            reranked: data.retrieval?.reranked ?? 0,
            confidence: data.retrieval?.confidence ?? 0,
            reranker_used: data.retrieval?.reranker_used ?? false,
            attempts: data.crag?.attempts ?? 1,
            rewritten: data.crag?.rewritten ?? false,
            decision: data.crag?.final_decision ?? 'grounded',
            latency: data.latency || null,
          };
          setRagMeta(currentRagMeta);
        }
        setLocalMessages((prev) => [
          ...prev,
          {
            id: `asst-${Date.now()}`,
            role: 'assistant',
            content: finalContent,
            created_at: new Date().toISOString(),
            citations: citations.length > 0 ? citations : undefined,
            ragMeta: currentRagMeta || undefined,
          },
        ]);
        setStreamingDisplay(null);
        streamingContentRef.current = '';
        pendingCitationsRef.current = [];
        setActiveToolEvents([]);

        queryClient.invalidateQueries({ queryKey: ['threads'] });
        queryClient.invalidateQueries({ queryKey: ['thread', activeThreadId] });
        queryClient.invalidateQueries({ queryKey: ['messages', activeThreadId] });

        // Navigate AFTER streaming so we don't unmount mid-stream
        if (isNewThread) {
          navigate(`/chat/${activeThreadId}`, { replace: true });
        }
      },
      // Tool SSE callbacks
      onToolStarted: (data) => {
        setActiveToolEvents((prev) => [
          ...prev.filter(t => t.tool !== data.tool),
          { tool: data.tool, input: data.input, status: 'running', id: Date.now() },
        ]);
      },
      onToolResult: (data) => {
        setActiveToolEvents((prev) =>
          prev.map((t) =>
            t.tool === data.tool
              ? { ...t, status: data.success ? 'success' : 'failed', data: data.data, error: data.error, source: data.source }
              : t
          )
        );
      },
      onToolError: (data) => {
        setActiveToolEvents((prev) =>
          prev.map((t) =>
            t.tool === data.tool ? { ...t, status: 'failed', error: data.error } : t
          )
        );
      },
      // RAG SSE callbacks
      onCitation: (cit) => {
        pendingCitationsRef.current = [...pendingCitationsRef.current, cit];
      },
      onGrading: (data) => {
        setRagMeta(prev => ({ ...prev, confidence: data.confidence, decision: data.relevant ? 'grounded' : 'insufficient' }));
      },
      onCragRetry: (data) => {
        setRagMeta(prev => ({ ...prev, attempts: data.attempt }));
      },
      // Phase 10 Research SSE callbacks
      onResearchStarted: (data) => {
        setIsResearching(true);
        setResearchEvents(prev => [...prev, { type: 'research_started', data }]);
      },
      onResearchPlanning: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_planning', data }]);
      },
      onResearchPlanCreated: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_plan_created', data }]);
      },
      onResearchTaskStarted: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_task_started', data }]);
      },
      onResearchTaskProgress: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_task_progress', data }]);
      },
      onResearchTaskCompleted: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_task_completed', data }]);
      },
      onResearchTaskFailed: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_task_failed', data }]);
      },
      onResearchEvidenceCollected: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_evidence_collected', data }]);
      },
      onResearchVerificationStarted: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_verification_started', data }]);
      },
      onResearchVerificationComplete: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_verification_complete', data }]);
      },
      onResearchRetry: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_retry', data }]);
      },
      onResearchSynthesisStarted: (data) => {
        setResearchEvents(prev => [...prev, { type: 'research_synthesis_started', data }]);
      },
      onResearchCitation: (data) => {
        setResearchCitations(prev => [...prev, data]);
        setResearchEvents(prev => [...prev, { type: 'research_citation', data }]);
      },
      onResearchComplete: (data) => {
        setIsResearching(false);
        setResearchEvents(prev => [...prev, { type: 'research_complete', data }]);
      },
      onResearchCancelled: (data) => {
        setIsResearching(false);
        setResearchEvents(prev => [...prev, { type: 'research_cancelled', data }]);
      },
      onResearchError: (data) => {
        setIsResearching(false);
        setResearchEvents(prev => [...prev, { type: 'research_error', data }]);
      },
      // Phase 12 Coding callbacks
      onCodingStarted: (data) => {
        setIsCoding(true);
        setCodingEvents(prev => [...prev, { type: 'coding_started', data }]);
      },
      onCodingFile: (data) => {
        setCodingEvents(prev => [...prev, { type: 'coding_file', data }]);
      },
      onCodingContextReady: (data) => {
        setCodingEvents(prev => [...prev, { type: 'coding_context_ready', data }]);
      },
      onCodingGeneration: (data) => {
        setCodingEvents(prev => [...prev, { type: 'coding_generation', data }]);
      },
      onCodingComplete: (data) => {
        setIsCoding(false);
        setCodingEvents(prev => [...prev, { type: 'coding_complete', data }]);
      },
      onCodingError: (data) => {
        setIsCoding(false);
        setCodingEvents(prev => [...prev, { type: 'coding_error', data }]);
      },
      // GPT-Style Memory callbacks
      onMemorySaved: (data) => {
        queryClient.invalidateQueries({ queryKey: ['memories'] });
        if (!data.explicit) {
          setMemoryToast(`Saved to memory: ${data.value}`);
          setTimeout(() => setMemoryToast(null), 4000);
        }
      },
      onMemoryForgotten: (data) => {
        queryClient.invalidateQueries({ queryKey: ['memories'] });
      },
      onError: (err) => {

        console.error('[ChatRoute] SSE error:', err);
        setIsResearching(false);
        setIsCoding(false);
        const partial = streamingContentRef.current;
        setLocalMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: (partial || '') + (partial ? '\n\n' : '') + `⚠️ Error: ${err.message}`,
            created_at: new Date().toISOString(),
          },
        ]);
        setStreamingDisplay(null);
        streamingContentRef.current = '';
        if (isNewThread) {
          navigate(`/chat/${activeThreadId}`, { replace: true });
        }
      },
    });
  }, [threadId, isStreaming, provider, model, mode, navigate, queryClient, streamChat, uploadedFiles, isTemporaryChat, webSearchEnabled]);

  const renderContent = (content) => (
    <div className="prose prose-invert max-w-none text-sm leading-relaxed
      prose-p:my-1 prose-headings:text-gray-100 prose-strong:text-gray-100
      prose-a:text-accent">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          code: CodeBlock,
          pre: ({ children }) => <>{children}</>,
        }}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  );

  const isStreamingActive = streamingDisplay !== null;
  const isNewChat = !threadId && localMessages.length === 0 && !isStreamingActive;

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden">
      {/* Premium Ambient Hero Background for Home / New Chat */}
      {isNewChat && <TarkAmbientBackground mode={mode} />}

      {/* Header */}
      <header className="h-14 border-b border-white/[0.05] flex items-center justify-between px-5 shrink-0 bg-[#000000]/95 backdrop-blur-sm z-10">
        <div className="flex items-center gap-3 truncate max-w-md">
          <h1 className="text-[13px] font-semibold text-[#F4F2ED] tracking-[-0.01em] truncate">
            {threadLoading ? 'Loading…' : threadData?.title || (threadId ? 'Chat' : 'New Chat')}
          </h1>
          {mode === 'coding' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-accent/10 border border-accent/25 text-accent rounded-full text-[11px] font-semibold shrink-0">
              <Code2 size={11} />
              <span>Coding</span>
            </span>
          )}
          {activeProject && (
            <button
              onClick={() => navigate(`/projects/${activeProject.id}`)}
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-[#141415] border border-accent/20 text-accent/90 rounded-full text-[11px] font-medium hover:border-accent/50 hover:text-accent transition-all shrink-0"
              title="View project workspace"
            >
              <span>{activeProject.avatar || '📁'}</span>
              <span className="truncate max-w-[140px]">{activeProject.name}</span>
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <>
              <button
                onClick={() => setIsTemporaryChat(!isTemporaryChat)}
                title={isTemporaryChat ? "Temporary chat enabled: memory writing disabled" : "Enable temporary chat (incognito memory)"}
                className={clsx(
                  "text-[11px] px-2.5 py-1 rounded-lg border flex items-center gap-1.5 transition-all font-medium",
                  isTemporaryChat
                    ? "bg-amber-500/10 border-amber-500/30 text-amber-300/90"
                    : "border-white/[0.06] bg-[#101011] hover:bg-[#141415] text-[#A0A0A0] hover:text-[#F4F2ED]"
                )}
              >
                <EyeOff size={12} />
                <span>{isTemporaryChat ? 'Incognito On' : 'Incognito'}</span>
              </button>
              <button
                onClick={toggleContextPanel}
                className="text-[11px] px-2.5 py-1 rounded-lg border border-white/[0.06] bg-[#101011] hover:bg-[#141415] text-[#A0A0A0] hover:text-[#F4F2ED] transition-all font-medium"
              >
                Context
              </button>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate('/login')}
                className="text-xs font-medium text-[#A0A0A0] hover:text-[#F4F2ED] px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
              >
                Sign in
              </button>
              <button
                onClick={() => navigate('/signup')}
                className="text-xs font-semibold text-black bg-[#C9A86A] hover:bg-[#E1C27A] px-3.5 py-1.5 rounded-lg transition-all shadow-[0_2px_10px_rgba(201,168,106,0.15)] cursor-pointer"
              >
                Get started
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Temporary Chat Privacy Banner */}
      {isTemporaryChat && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-1.5 text-center text-xs text-amber-300/90 flex items-center justify-center gap-2 relative z-10">
          <EyeOff size={13} />
          <span>Temporary Chat Active — Conversation turns will not be extracted or stored in long-term memory.</span>
        </div>
      )}

      {/* Subtle Auto-Memory Indicator Toast */}
      {memoryToast && (
        <div className="bg-accent/15 border-b border-accent/30 px-4 py-1.5 text-center text-xs text-accent flex items-center justify-center gap-2 animate-fadeIn transition-all relative z-10">
          <Sparkles size={13} className="text-accent" />
          <span className="font-medium">{memoryToast}</span>
        </div>
      )}

      {/* Message area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 relative z-10 flex flex-col justify-center">
        {isNewChat ? (
          <div className="relative flex items-center justify-center min-h-[calc(100vh-14rem)] max-w-7xl mx-auto w-full px-4 py-4 gap-0 lg:gap-8">
            {/* Hero ambient atmospheric glow */}
            <div className="hero-ambient" aria-hidden="true" />

            {/* Hero Main Content — Left Column */}
            <div className="flex-1 flex flex-col items-center lg:items-start justify-center text-center lg:text-left w-full max-w-full lg:max-w-[780px] xl:max-w-[840px] min-w-0 z-10 animate-fade-up">
              {/* Dynamic Time-based Greeting */}
              <div className="inline-flex items-center gap-2 select-none mb-4 sm:mb-4.5">
                <span className="w-[5px] h-[5px] rounded-full bg-accent animate-subtle-pulse shrink-0" />
                <span className="text-[15px] sm:text-[15.5px] font-semibold tracking-[-0.01em] text-[#D8D4CC]">
                  {(() => {
                    const hr = new Date().getHours();
                    const greet =
                      hr >= 5 && hr < 12
                        ? 'Good morning'
                        : hr >= 12 && hr < 17
                        ? 'Good afternoon'
                        : hr >= 17 && hr < 21
                        ? 'Good evening'
                        : 'Good night';
                    const name = isAuthenticated
                      ? user?.name || userSettingsEnvelope?.settings?.display_name || 'Developer'
                      : 'Developer';
                    return (
                      <>
                        <span>{greet}, </span>
                        <span>{name}</span>
                        <span className="text-accent font-bold">.</span>
                      </>
                    );
                  })()}
                </span>
              </div>

              {/* Hero Title & Tagline */}
              <div className="space-y-2.5 sm:space-y-3 mb-6 sm:mb-7">
                <h1 className="text-[32px] sm:text-[42px] md:text-[50px] lg:text-[54px] xl:text-[64px] 2xl:text-[68px] font-medium tracking-[-0.035em] text-[#E8E5DF] leading-[1.02] sm:whitespace-nowrap">
                  How can I help you{' '}
                  <span className="font-serif-italic text-accent inline-block">
                    today?
                  </span>
                </h1>
                <p className="text-[#9B9892] text-[14.5px] sm:text-[15.5px] font-normal tracking-[0.01em]">
                  Think deeper. Build smarter.
                </p>
              </div>

              {/* 6 Suggestion Action Cards in 3x2 Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 w-full">
                {[
                  {
                    icon: BookOpen,
                    title: 'Explain a concept',
                    desc: 'Clear, step-by-step explanations',
                    prompt: 'Explain the concept of ',
                    microClass: 'micro-glow',
                  },
                  {
                    icon: FileText,
                    title: 'Analyze a document',
                    desc: 'Understand PDFs, images, and more',
                    prompt: 'Help me analyze this document: ',
                    microClass: 'micro-scan',
                  },
                  {
                    icon: Code2,
                    title: 'Write or debug code',
                    desc: 'Build, fix, and optimize with AI',
                    prompt: 'Help me write or debug this code: ',
                    microClass: 'micro-terminal',
                  },
                  {
                    icon: Globe,
                    title: 'Research a topic',
                    desc: 'In-depth, reliable information',
                    prompt: 'Conduct in-depth research on ',
                    microClass: 'micro-orbit',
                  },
                  {
                    icon: Database,
                    title: 'Work with your data',
                    desc: 'Analyze and visualize datasets',
                    prompt: 'Help me analyze and visualize this data: ',
                    microClass: 'micro-node',
                  },
                  {
                    icon: Sparkles,
                    title: 'Create anything',
                    desc: 'Code, write, research and more',
                    prompt: 'Help me create ',
                    microClass: 'micro-spark',
                  },
                ].map((c, i) => {
                  const Icon = c.icon;
                  return (
                    <button
                      key={c.title}
                      type="button"
                      style={{ animationDelay: `${i * 45}ms` }}
                      onClick={() => {
                        setInputMessage(c.prompt);
                        if (textareaRef.current) {
                          textareaRef.current.focus();
                          setTimeout(() => {
                            if (textareaRef.current) {
                              textareaRef.current.style.height = 'auto';
                              textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 256) + 'px';
                            }
                          }, 10);
                        }
                      }}
                      className="action-card group relative bg-[#0B0B0B] hover:bg-[#121212] border border-white/[0.05] hover:border-accent/30 rounded-[18px] p-4 text-left cursor-pointer hover:shadow-[0_8px_32px_rgba(0,0,0,0.45),0_2px_12px_rgba(201,168,106,0.06)] flex flex-col gap-2 min-h-[88px] animate-fade-up overflow-hidden"
                    >
                      {/* Very subtle champagne left accent on hover */}
                      <div className="absolute left-0 top-[22%] bottom-[22%] w-[2px] bg-accent/0 group-hover:bg-accent/40 rounded-full transition-all duration-200" />
                      <div className="flex items-center gap-2.5">
                        <div className={clsx("text-[#77736D] group-hover:text-accent transition-colors duration-150 shrink-0", c.microClass)}>
                          <Icon size={14} strokeWidth={1.75} />
                        </div>
                        <div className="text-[14px] font-editorial font-[450] text-[#F2F0EB] group-hover:text-white tracking-[-0.018em] leading-[1.25] transition-colors duration-150">
                          {c.title}
                        </div>
                      </div>
                      <div className="text-[12.5px] font-normal text-[#A3A09A] leading-[1.5] line-clamp-2 pl-[24px]">
                        {c.desc}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Spline 3D Robot Assistant — Right Column */}
            <div className="hidden lg:flex flex-col items-center justify-center flex-shrink-0 w-[260px] xl:w-[300px] 2xl:w-[340px] pointer-events-none select-none">
              <SplineRobot />
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto w-full space-y-6 pb-4">
            {messagesLoading && (
              <div className="text-center text-[#767676] text-sm py-8">Loading messages…</div>
            )}

            {localMessages.map((msg, idx) => (
              <div key={msg.id || idx} className={clsx('flex gap-3 w-full', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                {msg.role === 'assistant' && (
                  <TarkAssistantAvatar size={40} className="mt-0.5" />
                )}
                <div className={clsx(
                  'max-w-[85%] rounded-2xl text-sm',
                  compactMessages ? 'px-3 py-2 text-xs' : chatDensity === 'spacious' ? 'px-5 py-4' : 'px-4 py-3',
                  msg.role === 'user' ? 'bg-[#141415] border border-white/[0.06] text-[#F4F2ED]' : 'bg-transparent text-[#F4F2ED]'
                )}>
                  {/* Attached Files / Screenshots in User Message */}
                  {showAttachmentPreviews && msg.attachments && msg.attachments.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-2.5">
                      {msg.attachments.map((att, i) => {
                        const isImg =
                          (att.mime_type && att.mime_type.startsWith('image/')) ||
                          /\.(png|jpe?g|webp|gif)$/i.test(att.filename || '');
                        const fileUrl = fileApi.getFileContentUrl(att.file_id || att.id, user?.id || DEV_USER_ID);
                        return isImg ? (
                          <a
                            key={att.file_id || att.id || i}
                            href={fileUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="group relative block overflow-hidden rounded-xl border border-white/[0.08] bg-black/40 hover:border-accent transition-all max-w-[280px] shadow-md"
                            title="Click to view full image"
                          >
                            <img
                              src={fileUrl}
                              alt={att.filename || 'attachment'}
                              className="max-h-56 w-auto rounded-lg object-contain bg-black/30 mx-auto"
                              loading="lazy"
                            />
                            {att.filename && (
                              <div className="px-2.5 py-1 text-[10px] text-[#A0A0A0] truncate bg-[#141415]/95 border-t border-white/[0.06] font-mono">
                                {att.filename}
                              </div>
                            )}
                          </a>
                        ) : (
                          <a
                            key={att.file_id || att.id || i}
                            href={fileUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#141415] border border-white/[0.08] text-xs text-[#F4F2ED] hover:border-accent transition-all"
                            title="Open attachment"
                          >
                            <FileText size={14} className="text-accent shrink-0" />
                            <span className="truncate max-w-[180px]">{att.filename || 'Document'}</span>
                          </a>
                        );
                      })}
                    </div>
                  )}

                  {renderContent(msg.content)}

                  {/* Message Timestamps */}
                  {showTimestamps && msg.created_at && (
                    <div className={clsx("text-[10px] text-[#767676] mt-1.5", msg.role === 'user' ? 'text-right' : 'text-left')}>
                      {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  )}

                  {/* Research Citations */}
                  {showCitationsSetting && msg.research_citations && msg.research_citations.length > 0 && (
                    <ResearchCitations citations={msg.research_citations} />
                  )}
                  {/* RAG Citations */}
                  {showCitationsSetting && msg.citations && msg.citations.length > 0 && (!msg.research_citations || msg.research_citations.length === 0) && (
                    <div className="mt-3 pt-2 border-t border-white/[0.06] space-y-1">
                      <div className="text-[10px] font-semibold text-[#A0A0A0] uppercase tracking-wider mb-1">Sources</div>
                      {msg.citations.map((cit, ci) => (
                        <div key={cit.chunk_id || ci} className="flex items-start gap-1.5 text-[11px] text-[#A0A0A0]">
                          <span className="text-accent shrink-0">▸</span>
                          <span><span className="text-[#F4F2ED]">{cit.filename}</span> · p.{cit.page_number} · {Math.round((cit.similarity_score || 0) * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* CRAG Debug / Pipeline Observability Panel */}
                  {msg.ragMeta && (
                    <CRAGDebugPanel ragMeta={msg.ragMeta} latency={msg.ragMeta?.latency} />
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full bg-[#141415] border border-white/[0.08] text-[#A0A0A0] flex items-center justify-center text-xs font-bold shrink-0 mt-1">U</div>
                )}
              </div>
            ))}

            {/* Live streaming bubble */}
            {isStreamingActive && (
              <div className="flex gap-3 w-full justify-start">
                <TarkAssistantAvatar size={40} className="mt-0.5" />
                <div className="max-w-[85%] rounded-2xl px-4 py-3 text-sm bg-transparent text-[#F4F2ED] flex-1">
                  {/* Research progress indicator (Deep Research mode) */}
                  {(isResearching || researchEvents.length > 0) && (
                    <ResearchProgress events={researchEvents} isActive={isResearching} />
                  )}
                  {/* Coding progress indicator (Coding mode) */}
                  {(isCoding || codingEvents.length > 0) && (
                    <CodingProgress events={codingEvents} isActive={isCoding} />
                  )}
                  {/* Tool execution indicators */}
                  {activeToolEvents.length > 0 && (
                    <div className="mb-3 space-y-1.5">
                      {activeToolEvents.map((evt, idx) => (
                        <div
                          key={evt.id || idx}
                          className={clsx(
                            "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono border transition-all mr-2 mb-1",
                            evt.status === 'running'
                              ? "bg-[#18181D] border-accent/40 text-[#E7CA82] shadow-sm animate-pulse"
                              : evt.status === 'success'
                              ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
                              : "bg-rose-950/40 border-rose-800/40 text-rose-300"
                          )}
                        >
                          <span className="text-[11px]">🔧</span>
                          <span className="font-semibold">{evt.tool}</span>
                          {evt.status === 'running' && (
                            <span className="text-[10px] text-[#A0A0A0] italic">executing…</span>
                          )}
                          {evt.status === 'success' && (
                            <span className="text-[10px] text-emerald-400">✓ complete</span>
                          )}
                          {evt.status === 'failed' && (
                            <span className="text-[10px] text-rose-400">✕ failed</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {streamingDisplay
                    ? <>{renderContent(streamingDisplay)}<span className="inline-block w-1 h-4 ml-0.5 align-middle bg-accent animate-pulse" /></>
                    : (
                      <span className="flex gap-1.5 items-center py-2">
                        <span className="w-1.5 h-1.5 bg-accent/70 rounded-full animate-bounce [animation-delay:0ms]" />
                        <span className="w-1.5 h-1.5 bg-accent/70 rounded-full animate-bounce [animation-delay:150ms]" />
                        <span className="w-1.5 h-1.5 bg-accent/70 rounded-full animate-bounce [animation-delay:300ms]" />
                      </span>
                    )
                  }
                </div>
              </div>
            )}

            {/* Completed research progress (shown after streaming ends) */}
            {!isStreamingActive && researchEvents.length > 0 && (
              <ResearchProgress events={researchEvents} isActive={false} />
            )}

            {/* Completed coding progress (shown after streaming ends) */}
            {!isStreamingActive && codingEvents.length > 0 && (
              <CodingProgress events={codingEvents} isActive={false} />
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="shrink-0 px-4 pb-5 relative z-10">
        {streamError && (
          <div className="max-w-3xl mx-auto mb-2 text-[11px] text-red-400 bg-red-400/8 border border-red-400/15 rounded-xl px-3 py-1.5 text-center">
            {streamError}
          </div>
        )}
        {pasteError && (
          <div className="max-w-3xl mx-auto mb-2 text-[11px] text-red-400 bg-red-400/8 border border-red-400/15 rounded-xl px-3 py-1.5 text-center">
            {pasteError}
          </div>
        )}
        <div
          className="max-w-3xl mx-auto w-full"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <FileList files={uploadedFiles} onRemove={handleRemoveFile} />
          {isUploadingAttachment && (
            <div className="flex items-center gap-2 px-3 py-1.5 mb-2 bg-[#141415] border border-accent/20 rounded-xl text-[11px] text-accent/90 animate-pulse">
              <Loader2 size={12} className="animate-spin" />
              <span>Uploading attachment…</span>
            </div>
          )}
          <div className={clsx(
            "composer-wrap bg-[#0D0D0D] backdrop-blur-xl border rounded-[20px] px-4 pt-4 pb-3 transition-all duration-200",
            isDragging
              ? "border-accent/40 shadow-[0_0_40px_rgba(201,168,106,0.12)] bg-accent/5"
              : ""
          )}>
            <textarea
              ref={textareaRef}
              value={inputMessage}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder="Ask anything…"
              disabled={isStreaming}
              className="w-full bg-transparent resize-none outline-none text-[14px] leading-relaxed min-h-[28px] max-h-64 text-[#F2F0EB] placeholder:text-[#5A5752] disabled:opacity-50 font-sans tracking-[-0.012em]"
              rows={1}
            />
            <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-white/[0.04]">
              <div className="flex items-center gap-1.5">
                <FileUploader onUploadSuccess={handleUploadSuccess} storageProvider={chatStorageProvider} />
                <button
                  type="button"
                  onClick={toggleChatStorageProvider}
                  className={clsx(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11.5px] font-medium border transition-all select-none cursor-pointer",
                    chatStorageProvider === 'local'
                      ? "bg-[#141415] text-[#A3A09A] hover:text-[#F2F0EB] border-white/[0.06] hover:border-white/[0.12]"
                      : "bg-[#161410] text-accent border-accent/30 hover:border-accent/50"
                  )}
                  title={`Storage Provider: ${chatStorageProvider === 'local' ? 'Local Disk' : 'Backblaze B2'} — click to toggle`}
                >
                  {chatStorageProvider === 'local' ? (
                    <>
                      <HardDrive size={11} className="text-[#77736D]" />
                      <span>Storage: Local</span>
                    </>
                  ) : (
                    <>
                      <Cloud size={11} className="text-accent" />
                      <span>Storage: B2</span>
                    </>
                  )}
                </button>
                <button
                  onClick={() => setWebSearchEnabled(v => !v)}
                  title={webSearchEnabled ? 'Web search ON — click to disable' : 'Enable web search'}
                  className={clsx(
                    'p-1.5 rounded-lg transition-all duration-150',
                    webSearchEnabled
                      ? 'text-accent bg-accent/10 border border-accent/20'
                      : 'text-[#77736D] hover:text-[#F2F0EB] hover:bg-[#141415]'
                  )}
                >
                  <Globe size={14} />
                </button>
                <div className="h-3.5 w-px bg-white/[0.06] mx-0.5" />
                <ModeModelSelector mode={mode} setMode={setMode} model={model} setModel={setModel} />
              </div>
              {isStreaming ? (
                <button onClick={stopStreaming} title="Stop generating"
                  className="w-8 h-8 flex items-center justify-center bg-[#141415] border border-white/[0.08] text-[#F2F0EB] rounded-full hover:bg-[#1C1C20] transition-all duration-150">
                  <Square size={13} fill="currentColor" />
                </button>
              ) : (
                <button
                  onClick={() => sendMessage(inputMessage)}
                  disabled={!inputMessage.trim() && uploadedFiles.length === 0}
                  title="Send"
                  className="w-8 h-8 flex items-center justify-center bg-accent text-[#080808] rounded-full hover:bg-accent-highlight active:scale-95 transition-all duration-150 disabled:opacity-20 disabled:cursor-not-allowed shadow-[0_2px_14px_rgba(201,168,106,0.25)]"
                >
                  <Send size={13} strokeWidth={2.2} />
                </button>
              )}
            </div>
          </div>
          <p className="text-center text-[11px] text-[#77736D] mt-2 tracking-[0.01em]">
            TARK AI can make mistakes. Verify important information.
          </p>
        </div>
      </div>
    </div>
  );
}
