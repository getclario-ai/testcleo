import React from 'react';
import { getFileTypeColor } from '../constants/colors';

function FileTypeChart({ files, title = "File Types" }) {
  if (!files || files.length === 0) {
    return (
      <div className="file-types">
        <h5>{title}</h5>
        <p className="no-files">No files found.</p>
      </div>
    );
  }

  // Group files by type with deduplication
  const types = {};
  files.forEach(file => {
    const type = file.fileType || 'Unknown';
    if (!types[type]) {
      types[type] = new Set();
    }
    types[type].add(file.id);
  });

  // Calculate total unique files for percentages
  const totalUniqueFiles = new Set(files.map(file => file.id)).size;

  return (
    <div className="file-types">
      <h5>{title}</h5>
      <div className="type-bars">
        {Object.entries(types)
          .filter(([_, fileIds]) => fileIds.size > 0)
          .sort((a, b) => b[1].size - a[1].size) // Sort by count descending (highest first)
          .map(([type, fileIds]) => {
            const count = fileIds.size;
            const percentage = totalUniqueFiles > 0 ? (count / totalUniqueFiles * 100) : 0;
            return (
              <div key={type} className="type-bar">
                <span className="type-label">{type.charAt(0).toUpperCase() + type.slice(1)}</span>
                <div className="bar-container">
                  <div 
                    className="bar" 
                    style={{ 
                      width: `${percentage}%`,
                      background: getFileTypeColor(type)
                    }}
                  ></div>
                </div>
                <div className="type-stats">
                  <span className="type-count">{count} files</span>
                  <span className="type-percentage">{percentage.toFixed(1)}%</span>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}

export default FileTypeChart;
