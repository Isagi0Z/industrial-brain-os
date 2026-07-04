import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

/**
 * Route guard for the authenticated app shell. Without this, an
 * unauthenticated visitor could reach any dashboard route directly (e.g. by
 * URL or a stale link) and every data fetch would send `Authorization:
 * Bearer null`, surfacing a raw backend JWT-decode error instead of a login
 * prompt. Redirects to /login, preserving the originally requested location
 * so LoginPage can send the user back after a successful sign-in.
 */
export const RequireAuth: React.FC = () => {
  const { token } = useAuth();
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
};
