import {
  createSiteGroupTranslation,
  deleteSiteGroupTranslation,
  listSiteGroupTranslations,
  updateSiteGroupTranslation,
} from '../api/site-group-translations';
import TranslationsEditor from './TranslationsEditor';

interface Props {
  groupId: string;
}

export default function SiteGroupTranslationsTab({ groupId }: Props) {
  return (
    <TranslationsEditor
      queryKey={['site-group-translations', groupId]}
      api={{
        list: () => listSiteGroupTranslations(groupId),
        create: (body) => createSiteGroupTranslation(groupId, body),
        update: (locale, body) => updateSiteGroupTranslation(groupId, locale, body),
        remove: (locale) => deleteSiteGroupTranslation(groupId, locale),
      }}
      emptyMessage="No group-wide translations yet. Sites in this group will use organisation or English defaults."
    />
  );
}
