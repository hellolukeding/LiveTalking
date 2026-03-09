import client from './client';

export interface AvatarMeta {
  avatar_id: string;
  name: string;
  tts_type: string;
  voice_id: string;
  created_at: string;
  updated_at?: string;
  status: 'creating' | 'ready' | 'error';
  error?: string | null;
  frame_count?: number;
}

export const listAvatars = async (): Promise<AvatarMeta[]> => {
  const res = await client.get('/avatars');
  return res.data.data ?? [];
};

export const getAvatar = async (id: string): Promise<AvatarMeta> => {
  const res = await client.get(`/avatars/${id}`);
  return res.data.data;
};

export const createAvatar = async (formData: FormData): Promise<{ avatar_id: string; status: string }> => {
  const res = await client.post('/avatars', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data.data;
};

export const updateAvatar = async (
  id: string,
  updates: Partial<Pick<AvatarMeta, 'name' | 'tts_type' | 'voice_id'>>
): Promise<AvatarMeta> => {
  const res = await client.put(`/avatars/${id}`, updates);
  return res.data.data;
};

export const deleteAvatar = async (id: string): Promise<void> => {
  await client.delete(`/avatars/${id}`);
};
