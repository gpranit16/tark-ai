import { Outlet } from 'react-router-dom';
import Sidebar from '../sidebar/Sidebar';
import ContextPanel from '../context/ContextPanel';
import ReminderNotificationListener from '../tasks/ReminderNotificationListener';
import { useAppStore } from '../../stores/useAppStore';

export default function Layout() {
  const isContextPanelOpen = useAppStore((state) => state.isContextPanelOpen);

  return (
    <div className="flex h-screen w-full bg-background text-gray-200 overflow-hidden font-sans">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 relative h-full">
        <Outlet />
      </main>
      {isContextPanelOpen && <ContextPanel />}
      <ReminderNotificationListener />
    </div>
  );
}
