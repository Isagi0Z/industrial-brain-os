export const formatRelativeTime = (date: Date | string): string => {
  const d = typeof date === 'string' ? new Date(date) : date;
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
};

export const normalizeAssetTag = (tag: string): string => {
  let cleaned = tag.trim().toUpperCase();
  cleaned = cleaned.replace(/[\s_]+/g, '-');
  
  if (cleaned.startsWith("VALVE-")) {
    cleaned = cleaned.replace("VALVE-", "VLV-");
  } else if (cleaned.startsWith("SENSOR-")) {
    cleaned = cleaned.replace("SENSOR-", "SEN-");
  } else if (cleaned.startsWith("PUMP-")) {
    cleaned = cleaned.replace("PUMP-", "P-");
  }
  return cleaned;
};
