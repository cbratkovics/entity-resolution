/** Allowlisted outbound links: only the two catalogue hosts, only for ids that match the contract patterns. */
import { A_ID, B_ID } from './contracts';

export const MUSICBRAINZ_HOST = 'https://musicbrainz.org/release-group/';
export const DISCOGS_HOST = 'https://www.discogs.com/master/';

export function musicbrainzLink(aId: string): string | null {
  return A_ID.test(aId) ? `${MUSICBRAINZ_HOST}${aId}` : null;
}

export function discogsLink(bId: string): string | null {
  return B_ID.test(bId) ? `${DISCOGS_HOST}${bId}` : null;
}
