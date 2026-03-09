import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  InboxOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { Alert, Button, Form, Input, Progress, Select, Steps, Typography, Upload, message as antMessage } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createAvatar } from '../api/avatar';

const { Title, Text } = Typography;
const { Dragger } = Upload;

const TTS_OPTIONS = [
  { label: 'Edge TTS (免费)', value: 'edge' },
  { label: 'Doubao TTS', value: 'doubao' },
  { label: '腾讯 TTS', value: 'tencent' },
  { label: 'Azure TTS', value: 'azure' },
];

const VOICE_PLACEHOLDERS: Record<string, string> = {
  edge: 'zh-CN-XiaoxiaoNeural',
  doubao: 'zh_female_xiaohe_uranus_bigtts',
  tencent: '1001',
  azure: 'zh-CN-XiaoxiaoNeural',
};

type Step = 'upload' | 'submitting' | 'done' | 'error';

export default function AvatarCreatePage() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreview, setVideoPreview] = useState<string>('');
  const [ttsType, setTtsType] = useState('edge');
  const [step, setStep] = useState<Step>('upload');
  const [progress, setProgress] = useState(0);
  const [, setCreatedId] = useState('');

  const handleVideoChange = (file: File) => {
    setVideoFile(file);
    const url = URL.createObjectURL(file);
    setVideoPreview(url);
    return false; // 阻止自动上传
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (!videoFile) {
        antMessage.warning('请先上传视频文件');
        return;
      }

      setStep('submitting');
      setProgress(10);

      const formData = new FormData();
      // avatar_id 由 name 自动生成（取下划线连接的小写）
      const autoId = `avatar_${values.name.toLowerCase().replace(/\s+/g, '_')}_${Date.now()}`;
      formData.append('avatar_id', autoId);
      formData.append('name', values.name);
      formData.append('tts_type', values.tts_type);
      formData.append('voice_id', values.voice_id || VOICE_PLACEHOLDERS[values.tts_type]);
      formData.append('video', videoFile);

      setProgress(40);

      const result = await createAvatar(formData);
      setProgress(100);
      setCreatedId(result.avatar_id);
      setStep('done');

    } catch (e: any) {
      setStep('error');
      antMessage.error('创建失败: ' + (e?.message ?? String(e)));
    }
  };

  const stepsItems = [
    { title: '上传视频' },
    { title: '配置信息' },
    { title: '开始生成' },
  ];

  const currentStepIndex = step === 'upload' ? 0 : step === 'submitting' ? 2 : 2;

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)',
        padding: '0 0 60px',
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
          <VideoCameraOutlined style={{ marginRight: 8, color: '#7c6aff' }} />
          新建数字人形象
        </Title>
      </div>

      <div style={{ maxWidth: 680, margin: '40px auto', padding: '0 24px' }}>
        {/* 进度步骤 */}
        <Steps
          current={currentStepIndex}
          items={stepsItems}
          style={{ marginBottom: 36 }}
          progressDot
        />

        {/* 生成完成状态 */}
        {step === 'done' && (
          <div
            style={{
              background: 'rgba(82, 196, 26, 0.1)',
              border: '1px solid rgba(82, 196, 26, 0.3)',
              borderRadius: 16,
              padding: 40,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
            <Title level={3} style={{ color: '#fff', marginBottom: 8 }}>生成任务已启动！</Title>
            <Text style={{ color: 'rgba(255,255,255,0.65)', display: 'block', marginBottom: 24 }}>
              数字人形象正在后台生成，通常需要 1~5 分钟，完成后状态将自动更新为"可用"。
            </Text>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <Button
                type="primary"
                size="large"
                onClick={() => navigate('/avatars')}
                style={{
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  border: 'none',
                  borderRadius: 10,
                }}
              >
                查看形象列表
              </Button>
              <Button
                size="large"
                onClick={() => {
                  setStep('upload');
                  setVideoFile(null);
                  setVideoPreview('');
                  form.resetFields();
                }}
                style={{ borderRadius: 10 }}
              >
                继续创建
              </Button>
            </div>
          </div>
        )}

        {/* 提交中 */}
        {step === 'submitting' && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Progress
              type="circle"
              percent={progress}
              strokeColor={{ '0%': '#667eea', '100%': '#764ba2' }}
            />
            <div style={{ marginTop: 24 }}>
              <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 16 }}>
                正在上传视频，请稍候...
              </Text>
            </div>
          </div>
        )}

        {/* 错误状态 */}
        {step === 'error' && (
          <Alert
            message="创建失败"
            description="请检查网络连接后重试，或确认视频文件格式正确。"
            type="error"
            showIcon
            action={
              <Button onClick={() => setStep('upload')}>重新尝试</Button>
            }
            style={{ marginBottom: 24, borderRadius: 12 }}
          />
        )}

        {/* 主表单 */}
        {(step === 'upload' || step === 'error') && (
          <Form
            form={form}
            layout="vertical"
            initialValues={{ tts_type: 'edge', voice_id: 'zh-CN-XiaoxiaoNeural' }}
          >
            {/* 视频上传 */}
            <div
              style={{
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 16,
                padding: 24,
                marginBottom: 24,
                border: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              <Title level={5} style={{ color: '#fff', marginBottom: 16 }}>
                1. 上传人物视频
              </Title>
              <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, display: 'block', marginBottom: 16 }}>
                支持 MP4 / MOV / AVI 格式，视频时长建议 5~60 秒，确保视频中有清晰的正面人脸。
              </Text>

              {!videoFile ? (
                <Dragger
                  accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi"
                  beforeUpload={handleVideoChange}
                  showUploadList={false}
                  style={{
                    background: 'rgba(124,106,255,0.08)',
                    borderColor: 'rgba(124,106,255,0.4)',
                    borderRadius: 12,
                  }}
                >
                  <p style={{ fontSize: 40, color: '#7c6aff' }}>
                    <InboxOutlined />
                  </p>
                  <p style={{ color: '#fff', fontSize: 16, fontWeight: 600, margin: '8px 0 4px' }}>
                    点击或拖拽视频文件到此处
                  </p>
                  <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: 13 }}>
                    MP4 / MOV / AVI，最大 500MB
                  </p>
                </Dragger>
              ) : (
                <div style={{ position: 'relative' }}>
                  <video
                    src={videoPreview}
                    controls
                    style={{ width: '100%', borderRadius: 12, maxHeight: 280, objectFit: 'cover' }}
                  />
                  <Button
                    size="small"
                    danger
                    style={{ position: 'absolute', top: 8, right: 8 }}
                    onClick={() => { setVideoFile(null); setVideoPreview(''); }}
                  >
                    重新选择
                  </Button>
                </div>
              )}
            </div>

            {/* 形象配置 */}
            <div
              style={{
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 16,
                padding: 24,
                border: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              <Title level={5} style={{ color: '#fff', marginBottom: 16 }}>
                2. 配置形象信息
              </Title>

              <Form.Item
                label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>形象名称</span>}
                name="name"
                rules={[{ required: true, message: '请输入形象名称' }]}
              >
                <Input placeholder="例如：小雅" size="large" style={{ borderRadius: 8 }} />
              </Form.Item>

              <Form.Item
                label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>语音引擎 (TTS)</span>}
                name="tts_type"
                rules={[{ required: true }]}
              >
                <Select
                  options={TTS_OPTIONS}
                  size="large"
                  style={{ borderRadius: 8 }}
                  onChange={(val) => {
                    setTtsType(val);
                    form.setFieldValue('voice_id', VOICE_PLACEHOLDERS[val]);
                  }}
                />
              </Form.Item>

              <Form.Item
                label={<span style={{ color: 'rgba(255,255,255,0.85)' }}>语音 ID / Voice</span>}
                name="voice_id"
                tooltip="不同 TTS 引擎的 Voice ID 格式不同，请参照对应服务文档"
              >
                <Input
                  placeholder={VOICE_PLACEHOLDERS[ttsType]}
                  size="large"
                  style={{ borderRadius: 8 }}
                />
              </Form.Item>
            </div>

            {/* 提交按钮 */}
            <div style={{ marginTop: 32, textAlign: 'center' }}>
              <Button
                type="primary"
                size="large"
                icon={<CloudUploadOutlined />}
                onClick={handleSubmit}
                disabled={!videoFile}
                style={{
                  background: videoFile
                    ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                    : undefined,
                  border: 'none',
                  borderRadius: 12,
                  height: 52,
                  paddingInline: 48,
                  fontSize: 16,
                  fontWeight: 600,
                  boxShadow: videoFile ? '0 4px 20px rgba(118,75,162,0.5)' : undefined,
                }}
              >
                上传并生成数字人形象
              </Button>
            </div>
          </Form>
        )}
      </div>
    </div>
  );
}
