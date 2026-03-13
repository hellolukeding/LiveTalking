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
  doubao: 'Doubao TTS',
  // Removed: edge, tencent, azure (no longer supported)
};

const StatusBadge = ({ status }: { status: AvatarMeta['status'] }) => {
  if (status === 'ready') return <Tag icon={<CheckCircleOutlined />} color="success">可用</Tag>;
  if (status === 'creating') return <Tag icon={<SyncOutlined spin />} color="processing">生成中</Tag>;
  return <Tag icon={<ExclamationCircleOutlined />} color="error">失败</Tag>;
};

const AvatarCardCover = ({ avatar }: { avatar: AvatarMeta }) => {
  const imagePath = avatar.image_path && avatar.status === 'ready' ? avatar.image_path : undefined;

  if (imagePath) {
    return (
      <img
        src={imagePath}
        alt={avatar.name}
        style={{
          width: '100%',
          height: 160,
          objectFit: 'cover',
        }}
        onError={(e) => {
          // 图片加载失败时回退到字母头像
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
      style={{
        width: '100%',
        height: 160,
        background: '#f5f5f5',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Avatar
        size={80}
        style={{
          background: '#5b4aff',
          fontSize: 36,
        }}
      >
        {avatar.name.charAt(0).toUpperCase()}
      </Avatar>
    </div>
  );
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
        background: '#ededed',
        padding: '0 0 40px',
      }}
    >
      {/* 顶部导航 */}
      <div
        style={{
          background: '#fff',
          borderBottom: '1px solid #e5e5e5',
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
            style={{ color: '#666', fontSize: 14 }}
          >
            返回对话
          </Button>
          <span style={{ color: '#ddd' }}>|</span>
          <Title level={4} style={{ margin: 0, color: '#333' }}>
            <UserOutlined style={{ marginRight: 8, color: '#5b4aff' }} />
            数字人形象管理
          </Title>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="large"
          onClick={() => navigate('/avatars/create')}
          style={{
            background: '#5b4aff',
            border: 'none',
            borderRadius: 8,
            fontWeight: 500,
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
            description="还没有数字人形象，点击右上角创建一个吧"
            style={{ paddingTop: 100 }}
          />
        ) : (
          <Row gutter={[24, 24]}>
            {avatars.map((avatar) => (
              <Col key={avatar.avatar_id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  style={{
                    background: '#fff',
                    border: '1px solid #e5e5e5',
                    borderRadius: 12,
                    overflow: 'hidden',
                  }}
                  styles={{ body: { padding: 20 } }}
                  cover={
                    <div style={{ position: 'relative' }}>
                      <AvatarCardCover avatar={avatar} />
                      {avatar.status === 'creating' && (
                        <div
                          style={{
                            position: 'absolute',
                            inset: 0,
                            background: 'rgba(255,255,255,0.9)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            gap: 8,
                          }}
                        >
                          <Spin size="large" />
                          <Text style={{ color: '#333', fontSize: 12 }}>正在生成...</Text>
                        </div>
                      )}
                    </div>
                  }
                  actions={[
                    <Tooltip title="编辑/查看详情" key="edit">
                      <EditOutlined
                        style={{ color: '#5b4aff', fontSize: 16 }}
                        onClick={() => navigate(`/avatars/${avatar.avatar_id}`)}
                      />
                    </Tooltip>,
                    <Tooltip title="删除形象" key="delete">
                      <DeleteOutlined
                        style={{ color: '#fa5151', fontSize: 16 }}
                        onClick={() => handleDelete(avatar)}
                      />
                    </Tooltip>,
                  ]}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Text strong style={{ color: '#333', fontSize: 16, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {avatar.name}
                      </Text>
                      <StatusBadge status={avatar.status} />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <Text style={{ color: '#999', fontSize: 12 }}>
                        语音：{TTS_LABELS[avatar.tts_type] ?? avatar.tts_type}
                      </Text>
                      <Text style={{ color: '#aaa', fontSize: 11 }} ellipsis>
                        Voice: {avatar.voice_id}
                      </Text>
                      {avatar.frame_count != null && avatar.frame_count > 0 && (
                        <Text style={{ color: '#bbb', fontSize: 11 }}>
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
