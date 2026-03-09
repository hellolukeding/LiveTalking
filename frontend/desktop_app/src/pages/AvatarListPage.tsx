import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  SyncOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Card, Col, Empty, message, Modal, Row, Spin, Tag, Tooltip, Typography } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AvatarMeta, deleteAvatar, listAvatars } from '../api/avatar';

const { Title, Text } = Typography;

const TTS_LABELS: Record<string, string> = {
  edge: 'Edge TTS',
  doubao: 'Doubao TTS',
  tencent: '腾讯 TTS',
  azure: 'Azure TTS',
};

const StatusBadge = ({ status }: { status: AvatarMeta['status'] }) => {
  if (status === 'ready') return <Tag icon={<CheckCircleOutlined />} color="success">可用</Tag>;
  if (status === 'creating') return <Tag icon={<SyncOutlined spin />} color="processing">生成中</Tag>;
  return <Tag icon={<ExclamationCircleOutlined />} color="error">失败</Tag>;
};

export default function AvatarListPage() {
  const navigate = useNavigate();
  const [avatars, setAvatars] = useState<AvatarMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchAvatars = useCallback(async () => {
    try {
      const list = await listAvatars();
      setAvatars(list);
    } catch (e) {
      console.error('[AvatarList] fetch error', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAvatars();
    // 每 4 秒轮询，直到没有处于 creating 状态的形象
    pollingRef.current = setInterval(() => {
      fetchAvatars();
    }, 4000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [fetchAvatars]);

  // 当所有形象都 ready 或 error 时停止轮询
  useEffect(() => {
    const hasCreating = avatars.some(a => a.status === 'creating');
    if (!hasCreating && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, [avatars]);

  const handleDelete = (avatar: AvatarMeta) => {
    Modal.confirm({
      title: `确认删除「${avatar.name}」？`,
      content: '删除后无法恢复，形象数据和图片将全部清除。',
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteAvatar(avatar.avatar_id);
          message.success('形象已删除');
          fetchAvatars();
        } catch (e) {
          message.error('删除失败: ' + String(e));
        }
      },
    });
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
        padding: '0 0 40px',
      }}
    >
      {/* 顶部导航 */}
      <div
        style={{
          background: 'rgba(255,255,255,0.06)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          padding: '16px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button
            type="text"
            icon={<VideoCameraOutlined />}
            onClick={() => navigate('/')}
            style={{ color: 'rgba(255,255,255,0.7)', fontSize: 14 }}
          >
            返回对话
          </Button>
          <span style={{ color: 'rgba(255,255,255,0.2)' }}>|</span>
          <Title level={4} style={{ margin: 0, color: '#fff' }}>
            <UserOutlined style={{ marginRight: 8, color: '#7c6aff' }} />
            数字人形象管理
          </Title>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="large"
          onClick={() => navigate('/avatars/create')}
          style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: 'none',
            borderRadius: 10,
            fontWeight: 600,
            boxShadow: '0 4px 16px rgba(118,75,162,0.5)',
          }}
        >
          新建形象
        </Button>
      </div>

      {/* 内容区 */}
      <div style={{ padding: '32px 40px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', paddingTop: 100 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : avatars.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Text style={{ color: 'rgba(255,255,255,0.5)' }}>还没有数字人形象，点击右上角创建一个吧</Text>}
            style={{ paddingTop: 100 }}
          />
        ) : (
          <Row gutter={[24, 24]}>
            {avatars.map((avatar) => (
              <Col key={avatar.avatar_id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  style={{
                    background: 'rgba(255,255,255,0.07)',
                    backdropFilter: 'blur(10px)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: 16,
                    overflow: 'hidden',
                    transition: 'all 0.3s ease',
                  }}
                  styles={{ body: { padding: 20 } }}
                  cover={
                    <div
                      style={{
                        height: 160,
                        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        position: 'relative',
                      }}
                    >
                      <Avatar
                        size={80}
                        style={{
                          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                          fontSize: 36,
                        }}
                      >
                        {avatar.name.charAt(0).toUpperCase()}
                      </Avatar>
                      {avatar.status === 'creating' && (
                        <div
                          style={{
                            position: 'absolute',
                            inset: 0,
                            background: 'rgba(0,0,0,0.5)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 8,
                          }}
                        >
                          <Spin size="large" />
                          <Text style={{ color: '#fff', fontSize: 12 }}>正在生成...</Text>
                        </div>
                      )}
                    </div>
                  }
                  actions={[
                    <Tooltip title="编辑/查看详情" key="edit">
                      <EditOutlined
                        style={{ color: '#7c6aff', fontSize: 16 }}
                        onClick={() => navigate(`/avatars/${avatar.avatar_id}`)}
                      />
                    </Tooltip>,
                    <Tooltip title="删除形象" key="delete">
                      <DeleteOutlined
                        style={{ color: '#ff4d4f', fontSize: 16 }}
                        onClick={() => handleDelete(avatar)}
                      />
                    </Tooltip>,
                  ]}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Text strong style={{ color: '#fff', fontSize: 16, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {avatar.name}
                      </Text>
                      <StatusBadge status={avatar.status} />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>
                        语音：{TTS_LABELS[avatar.tts_type] ?? avatar.tts_type}
                      </Text>
                      <Text style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11 }} ellipsis>
                        Voice: {avatar.voice_id}
                      </Text>
                      {avatar.frame_count != null && avatar.frame_count > 0 && (
                        <Text style={{ color: 'rgba(255,255,255,0.35)', fontSize: 11 }}>
                          {avatar.frame_count} 帧
                        </Text>
                      )}
                    </div>
                    {avatar.error && (
                      <Text type="danger" style={{ fontSize: 11 }} ellipsis>
                        错误：{avatar.error}
                      </Text>
                    )}
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </div>
    </div>
  );
}
