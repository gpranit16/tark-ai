import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Calendar, CheckCircle2, ExternalLink, Loader2, Unlink, RefreshCw, Clock, MapPin, AlertCircle, Shield } from 'lucide-react';
import clsx from 'clsx';
import { integrationsApi } from '../../api/integrationsApi';

export default function GoogleCalendarCard() {
  const queryClient = useQueryClient();
  const [isConnecting, setIsConnecting] = useState(false);
  const [actionError, setActionError] = useState(null);

  // Status Query
  const { data: status, isLoading: isStatusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ['integration-google-calendar-status'],
    queryFn: () => integrationsApi.getGoogleCalendarStatus(),
  });

  // Upcoming Events Query (only if connected)
  const isConnected = !!status?.connected;
  const { data: eventsData, isLoading: isEventsLoading, refetch: refetchEvents } = useQuery({
    queryKey: ['integration-google-calendar-events'],
    queryFn: () => integrationsApi.getUpcomingEvents({ maxResults: 5 }),
    enabled: isConnected,
  });

  // Disconnect Mutation
  const disconnectMutation = useMutation({
    mutationFn: () => integrationsApi.disconnectGoogleCalendar(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integration-google-calendar-status'] });
      queryClient.invalidateQueries({ queryKey: ['integration-google-calendar-events'] });
      setActionError(null);
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to disconnect Google Calendar');
    },
  });

  const handleConnect = async () => {
    setIsConnecting(true);
    setActionError(null);
    try {
      const data = await integrationsApi.getGoogleCalendarAuthUrl(true);
      if (data?.authorization_url) {
        window.location.href = data.authorization_url;
      } else {
        throw new Error('No authorization URL returned from server.');
      }
    } catch (err) {
      console.error('Failed to initiate Google OAuth:', err);
      setActionError(err.message || 'Failed to start Google OAuth connection');
      setIsConnecting(false);
    }
  };

  const handleDisconnect = () => {
    if (window.confirm('Are you sure you want to disconnect your Google Calendar?')) {
      disconnectMutation.mutate();
    }
  };

  const formatEventTime = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' · ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch (e) {
      return isoString;
    }
  };

  if (isStatusLoading) {
    return (
      <div className="bg-[#101012] border border-white/[0.06] rounded-2xl p-6 flex items-center justify-center min-h-[160px]">
        <Loader2 className="animate-spin text-accent" size={20} />
      </div>
    );
  }

  return (
    <div className="bg-[#101012] border border-white/[0.06] hover:border-white/[0.12] rounded-2xl p-6 transition-all duration-200">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-xl bg-[#18181C] border border-white/[0.08] flex items-center justify-center shadow-inner">
            <Calendar className="text-[#C9A86A]" size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-[15px] font-medium text-[#F2F0EB]">Google Calendar</h3>
              {isConnected && (
                <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                  <CheckCircle2 size={11} />
                  Connected
                </span>
              )}
            </div>
            <p className="text-[12.5px] text-[#85817B] mt-0.5 leading-relaxed">
              Personal OS calendar integration for schedule lookups, free/busy planning, and agenda synthesis.
            </p>
          </div>
        </div>

        {/* Action Button */}
        <div>
          {isConnected ? (
            <button
              onClick={handleDisconnect}
              disabled={disconnectMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-medium text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 border border-red-500/20 transition-all cursor-pointer disabled:opacity-50"
            >
              {disconnectMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Unlink size={12} />}
              <span>Disconnect</span>
            </button>
          ) : (
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-[12.5px] font-medium bg-accent text-[#080808] hover:bg-accent-highlight active:scale-95 transition-all shadow-[0_2px_14px_rgba(201,168,106,0.25)] cursor-pointer disabled:opacity-50"
            >
              {isConnecting ? <Loader2 size={13} className="animate-spin" /> : <Calendar size={13} />}
              <span>Connect Calendar</span>
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="mt-4 flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-[12px] text-red-400">
          <AlertCircle size={14} className="shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Connected Details & Live Schedule Preview */}
      {isConnected ? (
        <div className="mt-5 pt-5 border-t border-white/[0.04] space-y-4">
          <div className="flex flex-wrap items-center gap-4 text-[12px] text-[#A3A09A]">
            {status?.account_email && (
              <div className="flex items-center gap-1.5">
                <span className="text-[#77736D]">Account:</span>
                <span className="text-[#F2F0EB] font-mono font-medium">{status.account_email}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <Shield size={12} className="text-accent/80" />
              <span className="text-[#77736D]">Security:</span>
              <span className="text-[#F2F0EB]">AES Encrypted at rest</span>
            </div>
            {status?.created_at && (
              <div className="flex items-center gap-1.5">
                <span className="text-[#77736D]">Connected on:</span>
                <span>{new Date(status.created_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>

          {/* Upcoming Events Box */}
          <div className="bg-[#141416] border border-white/[0.04] rounded-xl p-3.5">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[12px] font-medium text-[#C9A86A] flex items-center gap-1.5">
                <Clock size={13} />
                Upcoming Calendar Agenda
              </span>
              <button
                onClick={() => refetchEvents()}
                className="text-[#77736D] hover:text-[#F2F0EB] transition-colors p-1"
                title="Refresh events"
              >
                <RefreshCw size={12} className={clsx(isEventsLoading && "animate-spin")} />
              </button>
            </div>

            {isEventsLoading ? (
              <div className="py-4 text-center text-[12px] text-[#77736D] flex items-center justify-center gap-2">
                <Loader2 size={12} className="animate-spin" />
                <span>Loading calendar schedule…</span>
              </div>
            ) : eventsData?.events && eventsData.events.length > 0 ? (
              <div className="space-y-2">
                {eventsData.events.map((evt) => (
                  <div
                    key={evt.id}
                    className="flex items-center justify-between gap-3 p-2 rounded-lg bg-[#19191D] hover:bg-[#202026] transition-colors text-[12px]"
                  >
                    <div className="truncate flex-1">
                      <p className="font-medium text-[#F2F0EB] truncate">{evt.summary}</p>
                      <div className="flex items-center gap-2 text-[11px] text-[#85817B] mt-0.5">
                        <span>{formatEventTime(evt.start)}</span>
                        {evt.location && (
                          <span className="flex items-center gap-1 truncate">
                            <MapPin size={10} />
                            {evt.location}
                          </span>
                        )}
                      </div>
                    </div>
                    {evt.html_link && (
                      <a
                        href={evt.html_link}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[#77736D] hover:text-accent p-1 shrink-0"
                        title="Open in Google Calendar"
                      >
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-[#77736D] py-2 italic text-center">
                No upcoming events in the next 7 days.
              </p>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-4 pt-4 border-t border-white/[0.04]">
          <ul className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11.5px] text-[#85817B]">
            <li className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent/60" />
              <span>Ask "What do I have tomorrow?"</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent/60" />
              <span>Query "Am I free at 5 PM?"</span>
            </li>
            <li className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent/60" />
              <span>Calendar-aware day planning</span>
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
