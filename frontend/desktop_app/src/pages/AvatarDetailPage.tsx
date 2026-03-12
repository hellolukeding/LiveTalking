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

const AvatarImage = ({ avatar }: { avatar: AvatarMeta }) => {
  const imagePath = avatar.image_path && avatar.status === 'ready' ? avatar.image_path : undefined;

  if (imagePath) {
    return (
      <img
        src={imagePath}
        alt={avatar.name}
        style={{
          width: 80,
          height: 80,
          borderRadius: '50%',
          objectFit: 'cover',
          flexShrink: 0,
        }}
        onError={(e) => {
          e.currentTarget.style.display = 'none';
          const fallback = e.currentTarget.parentElement?.querySelector('[data-fallback]');
          if (fallback) (fallback as HTMLElement).style.display = 'flex';
        }}
      />
    );
  }

  return (
    <div
      data-fallback
      style={{ display: imagePath ? 'none' : 'flex' }}
    >
      <Avatar
        size={80}
        style={{
          background: '#5b4aff',
          fontSize: 36,
          flexShrink: 0,
        }}
      >
        {avatar.name.charAt(0).toUpperCase()}
      </Avatar>
    </div>
  );
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
  }, [id, form]);

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

  return (
    <div style={{ minHeight: '100vh', background: '#ededed', padding: '0 0 60px' }}>
      {/* 顶部导航 */}
      <div
        style={{
          background: '#fff',
          borderBottom: '1px solid #e5e5e5',
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
          style={{ color: '#666' }}
        />
        <Title level={4} style={{ margin: 0, color: '#333' }}>
          <UserOutlined style={{ marginRight: 8, color: '#5b4aff' }} />
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
              background: '#fff',
              borderRadius: 12,
              padding: 32,
              border: '1px solid #e5e5e5',
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
                background: '#fff',
                borderRadius: 12,
                padding: 32,
                border: '1px solid #e5e5e5',
                marginBottom: 24,
                display: 'flex',
                alignItems: 'center',
                gap: 24,
              }}
            >
              <AvatarImage avatar={avatar} />
              <div style={{ flex: 1 }}>
                <Space align="center" style={{ marginBottom: 8 }}>
                  <Title level={3} style={{ margin: 0, color: '#333' }}>
                    {avatar.name}
                  </Title>
                  <StatusTag status={avatar.status} />
                </Space>
                <Descriptions
                  column={1}
                  size="small"
                  labelStyle={{ color: '#999', minWidth: 80 }}
                  contentStyle={{ color: '#666' }}
                >
                  <Descriptions.Item label="ID">
                    <Text code style={{ color: '#5b4aff' }}>{avatar.avatar_id}</Text>
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
                background: '#fff',
                borderRadius: 12,
                padding: 32,
                border: '1px solid #e5e5e5',
              }}
            >
              <Title level={5} style={{ color: '#333', marginBottom: 24 }}>
                编辑配置
              </Title>

              <Form form={form} layout="vertical">
                <Form.Item
                  label={<span style={{ color: '#666' }}>形象名称</span>}
                  name="name"
                  rules={[{ required: true, message: '请输入形象名称' }]}
                >
                  <Input size="large" style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item
                  label={<span style={{ color: '#666' }}>语音引擎 (TTS)</span>}
                  name="tts_type"
                  rules={[{ required: true }]}
                >
                  <Select options={TTS_OPTIONS} size="large" style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item
                  label={<span style={{ color: '#666' }}>语音 ID / Voice ID</span>}
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
                        background: '#5b4aff',
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
