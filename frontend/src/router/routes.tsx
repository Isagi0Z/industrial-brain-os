import { createBrowserRouter, Navigate } from "react-router-dom";
import { RequireAuth } from "../components/auth/RequireAuth";
import { DashboardLayout } from "../components/layout/DashboardLayout";
import { DocumentHub } from "../components/documents/DocumentHub";
import { DocumentDetails } from "../components/documents/DocumentDetails";
import { ChatInterface } from "../components/chat/ChatInterface";
import { KnowledgeGraphView } from "../components/graph/KnowledgeGraphView";
import { MaintenanceBrainPage } from "../components/brains/MaintenanceBrainPage";
import { ComplianceBrainPage } from "../components/brains/ComplianceBrainPage";
import { RcaBrainPage } from "../components/brains/RcaBrainPage";
import { LessonsBrainPage } from "../components/brains/LessonsBrainPage";
import { LandingPage } from "../pages/LandingPage";
import { LoginPage } from "../pages/LoginPage";
import { SignupPage } from "../pages/SignupPage";
import { SettingsPage } from "../pages/SettingsPage";
import { OverviewPage } from "../pages/OverviewPage";
import { EvaluationPage } from "../pages/EvaluationPage";
import { NotFound } from "../pages/NotFound";

export const router = createBrowserRouter([
  { path: "/", element: <LandingPage /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  {
    element: <RequireAuth />,
    errorElement: <NotFound />,
    children: [
      {
        element: <DashboardLayout />,
        children: [
          { path: "overview", element: <OverviewPage /> },
          { path: "evaluation", element: <EvaluationPage /> },
          { path: "documents", element: <DocumentHub /> },
          { path: "documents/:id", element: <DocumentDetails /> },
          { path: "knowledge", element: <ChatInterface /> },
          { path: "chat", element: <Navigate to="/knowledge" replace /> },
          { path: "knowledge-graph", element: <KnowledgeGraphView /> },
          { path: "settings", element: <SettingsPage /> },
          { path: "maintenance", element: <MaintenanceBrainPage /> },
          { path: "compliance", element: <ComplianceBrainPage /> },
          { path: "rca", element: <RcaBrainPage /> },
          { path: "lessons-learned", element: <LessonsBrainPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
