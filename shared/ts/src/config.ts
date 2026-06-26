export const API_BASE_URL = '/api/v1';

export const THEME_STORAGE_KEY = 'ib-ui-theme';

export const getAuthHeaders = (token?: string, correlationId?: string): Record<string, string> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (correlationId) {
    headers['X-Correlation-ID'] = correlationId;
  }
  return headers;
};
