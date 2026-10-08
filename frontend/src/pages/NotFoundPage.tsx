import { useNavigate } from 'react-router-dom';
import { PATHS } from '@/paths';
import { StatusPage } from './StatusPage';

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <StatusPage
      variant="alert"
      title="Pagina niet gevonden"
      message="Deze pagina bestaat niet of is verplaatst."
      action={{ text: 'Naar Stand van zaken', onClick: () => navigate(PATHS.statusOverview) }}
    />
  );
}
