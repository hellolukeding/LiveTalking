import { useNavigate } from 'react-router-dom';
import { Card, Col, message, Row, Spin, Tag, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { listAvatars, AvatarMeta } from '../api/avatar';

const { Title, Text } = Typography;

export default function AvatarSelectionPage() {
  const navigate = useNavigate();
  const [avatars, setAvatars] = useState<AvatarMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [imageErrors, setImageErrors] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadAvatars();
  }, []);

  const loadAvatars = async () => {
    try {
      const data = await listAvatars();
      const readyAvatars = data.filter(a => a.status === 'ready');
      setAvatars(readyAvatars);
    } catch (error) {
      message.error('加载头像列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAvatar = useCallback((avatarId: string) => {
    navigate(`/videochat?avatar_id=${avatarId}`);
  }, [navigate]);

  const handleImageError = useCallback((avatarId: string) => {
    setImageErrors(prev => new Set(prev).add(avatarId));
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (avatars.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Title level={3}>暂无可用数字人形象</Title>
        <Text type="secondary">请先在头像管理页面创建形象</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Title level={2}>选择数字人形象</Title>
      <Text type="secondary">点击下方卡片选择要使用的数字人形象</Text>

      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        {avatars.map((avatar) => (
          <Col xs={24} sm={12} md={8} lg={6} key={avatar.avatar_id}>
            <Card
              hoverable
              cover={avatar.image_path && !imageErrors.has(avatar.avatar_id) ? (
                <div style={{ height: '200px', overflow: 'hidden', background: '#f0f0f0' }}>
                  <img
                    alt={avatar.name}
                    src={avatar.image_path}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={() => handleImageError(avatar.avatar_id)}
                  />
                </div>
              ) : (
                <div style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f0f0' }}>
                  <Text type="secondary">{imageErrors.has(avatar.avatar_id) ? '图片加载失败' : '无预览图'}</Text>
                </div>
              )}
              onClick={() => handleSelectAvatar(avatar.avatar_id)}
              style={{ cursor: 'pointer' }}
            >
              <Card.Meta
                title={avatar.name || 'Unnamed Avatar'}
                description={
                  <div>
                    <Tag color="blue">{avatar.tts_type || 'edge'}</Tag>
                    <div style={{ marginTop: '8px' }}>
                      <Text type="secondary">ID: {avatar.avatar_id || 'Unknown'}</Text>
                    </div>
                    {avatar.frame_count && (
                      <div>
                        <Text type="secondary">帧数: {avatar.frame_count}</Text>
                      </div>
                    )}
                  </div>
                }
              />
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
