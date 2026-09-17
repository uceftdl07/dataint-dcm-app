import React from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';

const DatabricksInsightDetail: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams] = useSearchParams();

  if (!slug) {
    return <Navigate to="/databricks/insights" replace />;
  }

  const next = new URLSearchParams(searchParams);
  next.set('dashboard', slug);

  return <Navigate to={`/databricks/insights?${next.toString()}`} replace />;
};

export default DatabricksInsightDetail;
