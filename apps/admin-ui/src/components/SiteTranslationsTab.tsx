import {
  createTranslation,
  deleteTranslation,
  listTranslations,
  updateTranslation,
} from '../api/translations';
import { getTranslationInheritance } from '../api/sites';
import TranslationsEditor from './TranslationsEditor';

interface Props {
  siteId: string;
}

export default function SiteTranslationsTab({ siteId }: Props) {
  return (
    <TranslationsEditor
      queryKey={['sites', siteId, 'translations']}
      api={{
        list: () => listTranslations(siteId),
        create: (body) => createTranslation(siteId, body),
        update: (locale, body) => updateTranslation(siteId, locale, body),
        remove: (locale) => deleteTranslation(siteId, locale),
      }}
      getInheritance={(locale) => getTranslationInheritance(siteId, locale)}
    />
  );
}
