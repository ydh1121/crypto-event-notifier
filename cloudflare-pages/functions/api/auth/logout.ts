import {clearSessionCookie, deleteSession} from '../../lib/auth';
import {json} from '../../lib/http';
import type {Env} from '../../lib/types';

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  await deleteSession(env, request);
  return json({ok: true}, {headers: {'set-cookie': clearSessionCookie()}});
};
