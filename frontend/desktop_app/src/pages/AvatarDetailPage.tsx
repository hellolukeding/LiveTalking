import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SaveOutlined,
  SyncOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Avatar,
  Button,
  Descriptions,
  Form,
  Input,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
  message as antMessage
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AvatarMeta, getAvatar, updateAvatar } from '../api/avatar';

const { Title, Text } = Typography;

const TTS_OPTIONS = [
  { label: 'Edge TTS (免费)', value: 'edge' },
  { label: 'Doubao TTS', value: 'doubao' },
  { label: '腾讯 TTS', value: 'tencent' },
  { label: 'Azure TTS', value: 'azure' },
];

const StatusTag = ({ status }: { status: AvatarMeta['status'] }) => {
  if (status === 'ready') return <Tag icon={<CheckCircleOutlined />} color="success">可用</Tag>;
  if (status === 'creating') return <Tag icon={<SyncOutlined spin />} color="processing">生成中</Tag>;
  return <Tag icon={<ExclamationCircleOutlined />} color="error">生成失败</Tag>;
};

export default function AvatarDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [avatar, setAvatar] = useState<AvatarMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getAvatar(id)
      .then((meta) => {
        setAvatar(meta);
        form.setFieldsValue({ name: meta.name, tts_type: meta.tts_type, voice_id: meta.voice_id });
      })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const updated = await updateAvatar(id!, values);
      setAvatar(updated);
      antMessage.success('已保存');
    } catch (e: any) {
      antMessage.error('保存失败: ' + (e?.message ?? String(e)));
    } finally {
      setSaving(false);
    }
  };

  const gradientBg = 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)';

  return (
    <div style={{ minHeight: '100vh', background: gradientBg, padding: '0 0 60px' }}>
      {/* 顶部导航 */}
      <div
        style={{
          background: 'rgba(255,255,255,0.06)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          padding: '16px 32px',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}
      >
        <Button
          icon={<ArrowLeftOutlined />}
          type="text"
          onClick={() => navigate('/avatars')}
          style={{ color: 'rgba(255,255,255,0.7)' }}
        />
        <Title level={4} style={{ margin: 0, color: '#fff' }}>
          <UserOutlined style={{ marginRight: 8, color: '#7c6aff' }} />
          形象详情
        </Title>
      </div>

      <div style={{ maxWidth: 640, margin: '40px auto', padding: '0 24px' }}>
        {notFound && (
          <Alert
            message="形象不存在"
            description="未找到该数字人形象，可能已被删除。"
            type="error"
            showIcon
            action={<Button onClick={() => navigate('/avatars')}>返回列表</Button>}
          />
        )}

        {loading && !notFound && (
          <div
            style={{
              background: 'rgba(255,255,255,0.05)',
              borderRadius: 16,
              padding: 32,
              border: '1px solid rgba(255,255,255,0.1)',
            }}
          >
            <Skeleton active avatar={{ size: 80 }} paragraph={{ rows: 4 }} />
          </div>
        )}

        {!loading && avatar && (
          <>
            {/* 形象头像与基础信息 */}
            <div
              style={{
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 16,
                padding: 32,
                border: '1px solid rgba(255,255,255,0.1)',
                marginBottom: 24,
                display: 'flex',
                alignItems: 'center',
                gap: 24,
              }}
            >
              <Avatar
                size={80}
                style={{
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  fontSize: 36,
                  flexShrink: 0,
                }}
              >
                {avatar.name.charAt(0).toUpperCase()}
              </Avatar>
              <div style={{ flex: 1 }}>
                <Space align="center" style={{ marginBottom: 8 }}>
                  <Title level={3} style={{ margin: 0, color: '#fff' }}>
                    {avatar.name}
                  </Title>
                  <StatusTag status={avatar.status} />
                </Space>
                <Descriptions
                  column={1}
                  size="small"
                  labelStyle={{ color: 'rgba(255,255,255,0.45)', minWidth: 80 }}
                  contentStyle={{ color: 'rgba(255,255,255,0.7)' }}
                >
                  <Descriptions.Item label="ID">
                    <Text code style={{ color: '#a78bfa' }}>{avatar.avatar_id}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="帧数">
                    {avatar.frame_count != null && avatar.frame_count > 0 ? `${avatar.frame_count} 帧` : '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label="创建时间">
                    {new Date(avatar.created_at).toLocaleString('zh-CN')}
                  </Descriptions.Item>
                  {avatar.updated_at && (
                    <Descriptions.Item label="更新时间">
                      {new Date(avatar.updated_at).toLocaleString('zh-CN')}
                    </Descriptions.Item>
                  )}
                </Descriptions>
                {avatar.error && (
                  <Text type="danger" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                    错误信息：{avatar.error}
                  </Text>
                )}
              </div>
            </div>

            {/* 编辑表单 */}
            <div
              style={{
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 16,
                padding: 32,
                border: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              <Title level={5} style={{ color: '#fff', marginBottom: 24 }}>
                编辑配置
              </Title>

              <Form form={form} layout="vertical">
                <Form.Item
                  label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>形象名称</span>}
                  name="name"
                  rules={[{ required: true, message: '请输入形象名称' }]}
                >
                  <Input size="large" style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item
                  label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>语音引擎 (TTS)</span>}
                  name="tts_type"
                  rules={[{ required: true }]}
                >
                  <Select options={TTS_OPTIONS} size="large" style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item
                  label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>语音 ID / Voice ID</span>}
                  name="voice_id"
                  tooltip="语音 ID 与所选 TTS 引擎对应，如 Edge TTS 使用 zh-CN-XiaoxiaoNeural"
                >
                  <Input size="large" style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item style={{ marginTop: 32, textAlign: 'right' }}>
                  <Space>
                    <Button onClick={() => navigate('/avatars')} style={{ borderRadius: 8 }}>
                      取消
                    </Button>
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      onClick={handleSave}
                      loading={saving}
                      size="large"
                      style={{
                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        border: 'none',
                        borderRadius: 8,
                      }}
                    >
                      保存更改
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
