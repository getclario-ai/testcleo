import React from 'react';
import { getRiskCategoryColor } from '../constants/colors';

function RiskCategoryChart({ files, title = "Risk Categories" }) {
  if (!files || files.length === 0) {
    return (
      <div className="risk-categories">
        <h5>{title}</h5>
        <p className="no-files">No files found.</p>
      </div>
    );
  }

  // Group files by risk category with deduplication
  const risks = {};
  files.forEach(file => {
    if (file.sensitiveCategories && file.sensitiveCategories.length > 0) {
      file.sensitiveCategories.forEach(category => {
        if (!risks[category]) {
          risks[category] = new Set();
        }
        risks[category].add(file.id);
      });
    }
  });

  // Calculate total unique files for percentages
  const totalUniqueFiles = new Set(files.map(file => file.id)).size;

  if (Object.keys(risks).length === 0) {
    return (
      <div className="risk-categories">
        <h5>{title}</h5>
        <p className="no-files">No risk categories found.</p>
      </div>
    );
  }

  return (
    <div className="risk-categories">
      <h5>{title}</h5>
      <div className="type-bars">
        {Object.entries(risks)
          .filter(([_, fileIds]) => fileIds.size > 0)
          .sort((a, b) => b[1].size - a[1].size) // Sort by count descending (highest first)
          .map(([category, fileIds]) => {
            const count = fileIds.size;
            const percentage = totalUniqueFiles > 0 ? (count / totalUniqueFiles * 100) : 0;
            return (
              <div key={category} className="type-bar">
                <span className="type-label">{category.charAt(0).toUpperCase() + category.slice(1)}</span>
                <div className="bar-container">
                  <div 
                    className="bar" 
                    style={{ 
                      width: `${percentage}%`,
                      background: getRiskCategoryColor(category)
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

export default RiskCategoryChart;
