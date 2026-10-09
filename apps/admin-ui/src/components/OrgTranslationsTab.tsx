import {
  createOrgTranslation,
  deleteOrgTranslation,
  listOrgTranslations,
  updateOrgTranslation,
} from '../api/org-translations';
import TranslationsEditor from './TranslationsEditor';

export default function OrgTranslationsTab() {
  return (
    <TranslationsEditor
      queryKey={['org-translations']}
      api={{
        list: listOrgTranslations,
        create: createOrgTranslation,
        update: updateOrgTranslation,
        remove: deleteOrgTranslation,
      }}
      emptyMessage="No organisation-wide translations yet. Sites will use group or English defaults."
    />
  );
}
