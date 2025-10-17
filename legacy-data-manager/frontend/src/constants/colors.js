// Centralized color definitions for the entire application
// This is the SINGLE source of truth for all colors

export const FILE_TYPE_COLORS = {
  documents: '#4285F4',    // Google Blue
  spreadsheets: '#0F9D58', // Google Green  
  presentations: '#F4B400', // Google Yellow
  pdfs: '#DB4437',         // Google Red
  images: '#9C27B0',       // Purple
  others: '#757575',       // Gray
  videos: '#757575',       // Gray (not in main dashboard)
  audio: '#757575'         // Gray (not in main dashboard)
};

export const RISK_CATEGORY_COLORS = {
  pii: '#e74c3c',        // Red
  financial: '#f39c12',  // Orange
  legal: '#8e44ad',      // Purple
  confidential: '#c0392b' // Dark Red
};

export const STATUS_COLORS = {
  sensitive: '#DB4437',  // Red
  clean: '#0F9D58',      // Green
  default: '#757575'     // Gray
};

// CSS Custom Properties for CSS files
export const CSS_CUSTOM_PROPERTIES = `
  :root {
    --risk-pii: ${RISK_CATEGORY_COLORS.pii};
    --risk-financial: ${RISK_CATEGORY_COLORS.financial};
    --risk-legal: ${RISK_CATEGORY_COLORS.legal};
    --risk-confidential: ${RISK_CATEGORY_COLORS.confidential};
    --file-documents: ${FILE_TYPE_COLORS.documents};
    --file-spreadsheets: ${FILE_TYPE_COLORS.spreadsheets};
    --file-presentations: ${FILE_TYPE_COLORS.presentations};
    --file-pdfs: ${FILE_TYPE_COLORS.pdfs};
    --file-images: ${FILE_TYPE_COLORS.images};
    --file-others: ${FILE_TYPE_COLORS.others};
    --status-sensitive: ${STATUS_COLORS.sensitive};
    --status-clean: ${STATUS_COLORS.clean};
    --status-default: ${STATUS_COLORS.default};
  }
`;

// Helper functions for easy access
export const getFileTypeColor = (type) => {
  return FILE_TYPE_COLORS[type] || STATUS_COLORS.default;
};

export const getRiskCategoryColor = (category) => {
  return RISK_CATEGORY_COLORS[category?.toLowerCase()] || STATUS_COLORS.default;
};

export const getStatusColor = (status) => {
  return STATUS_COLORS[status] || STATUS_COLORS.default;
};
