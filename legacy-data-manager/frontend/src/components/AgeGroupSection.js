import React from 'react';
import FileTypeChart from './FileTypeChart';
import RiskCategoryChart from './RiskCategoryChart';

function AgeGroupSection({ files, ageLabel }) {
  if (!files || files.length === 0) {
    return (
      <div className="age-section">
        <h4>{ageLabel}</h4>
        <p className="no-files">No files found for this age group.</p>
      </div>
    );
  }

  return (
    <div className="age-section">
      <h4>{ageLabel}</h4>
      <div className="section-content file-types-card">
        <FileTypeChart files={files} title="File Categories" />
      </div>
      <div className="section-content">
        <RiskCategoryChart files={files} title="Risk Categories" />
      </div>
    </div>
  );
}

export default AgeGroupSection;
