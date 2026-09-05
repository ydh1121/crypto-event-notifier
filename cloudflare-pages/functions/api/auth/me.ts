import {getSession} from '../../lib/auth';
import {error, json} from '../../lib/http';
import type {Env} from '../../lib/types';

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  const session = await getSession(env, request);
  if (!session) return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.');
  return json({ok: true, user: session.user});
};
