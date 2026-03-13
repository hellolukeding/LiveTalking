import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  InboxOutlined,
  VideoCameraOutlined,
  InfoCircleOutlined,
  SoundOutlined,
} from '@ant-design/icons';
import { Alert, Button, Form, Input, Progress, Select, Space, Steps, Tooltip, Typography, Upload, message as antMessage } from 'antd';
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { createAvatar, previewVoiceTTS } from '../api/avatar';

const { Title, Text } = Typography;
const { Dragger } = Upload;

// Default Voice ID (温柔淑女)
const DEFAULT_VOICE_ID = 'zh_female_wenroushunshun_mars_bigtts';

// Common voice options for Doubao TTS
const VOICE_OPTIONS = [
  { label: '温柔淑女（推荐）', value: 'zh_female_wenroushunshun_mars_bigtts' },
  { label: '阳光青年', value: 'zh_male_yangguangqingnian_mars_bigtts' },
  { label: '甜美桃子', value: 'zh_female_tianmeitaozi_mars_bigtts' },
  { label: '爽快思思', value: 'zh_female_shuangkuaisisi_moon_bigtts' },
  { label: '知性女声', value: 'zh_female_zhixingnvsheng_mars_bigtts' },
  { label: '清爽男大', value: 'zh_male_qingshuangnanda_mars_bigtts' },
  { label: '京腔侃爷', value: 'zh_male_jingqiangkanye_moon_bigtts' },
  { label: '湾湾小何', value: 'zh_female_wanwanxiaohe_moon_bigtts' },
  { label: '广州德哥', value: 'zh_male_guozhoudege_moon_bigtts' },
  { label: '呆萌川妹', value: 'zh_female_daimengchuanmei_moon_bigtts' },
  { label: '自定义输入...', value: '__custom__' },
];

type Step = 'upload' | 'submitting' | 'done' | 'error';

export default function AvatarCreatePage() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreview, setVideoPreview] = useState<string>('');
  const [selectedVoice, setSelectedVoice] = useState(DEFAULT_VOICE_ID);
  const [customVoice, setCustomVoice] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const [step, setStep] = useState<Step>('upload');
  const [progress, setProgress] = useState(0);
  const [createdId, setCreatedId] = useState('');

  // Cleanup video preview URL on unmount
  useEffect(() => {
    return () => {
      if (videoPreview) {
        URL.revokeObjectURL(videoPreview);
      }
    };
  }, [videoPreview]);

  // Cleanup audio resources on unmount
  useEffect(() => {
    return () => {
      // Stop any playing audio
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      // Revoke blob URL
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, []);

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
      formData.append('tts_type', 'doubao');  // Changed from values.tts_type
      formData.append('voice_id', selectedVoice === '__custom__' ? customVoice : selectedVoice);
      formData.append('video', videoFile);

      setProgress(40);

      const result = await createAvatar(formData);
      setProgress(100);
      setCreatedId(result.avatar_id);
      setStep('done');

    } catch (e) {
      setStep('error');
      const errorMessage = e instanceof Error ? e.message : String(e);
      antMessage.error('创建失败: ' + errorMessage);
    }
  };

  const handlePreviewVoice = async (voiceId: string) => {
    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    // Revoke previous blob URL if exists
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }

    if (!voiceId || voiceId === '__custom__' || previewLoading) {
      return;
    }

    setPreviewLoading(true);
    try {
      const audioUrl = await previewVoiceTTS(voiceId);
      
      // Store refs for cleanup
      blobUrlRef.current = audioUrl;
      const audio = new Audio(audioUrl);
      audioRef.current = audio;
      
      // Handle play() promise rejection
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch((error) => {
          console.error('Audio play failed:', error);
          // Clean up on failure
          if (blobUrlRef.current) {
            URL.revokeObjectURL(blobUrlRef.current);
            blobUrlRef.current = null;
          }
          antMessage.error('音频播放失败，请检查浏览器自动播放设置');
        });
      }

      audio.onended = () => {
        // Clean up when audio finishes playing
        audioRef.current = null;
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current);
          blobUrlRef.current = null;
        }
      };
    } catch (e) {
      antMessage.error('试听失败: ' + (e instanceof Error ? e.message : String(e)));
    } finally {
      setPreviewLoading(false);
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
        background: '#ededed',
        padding: '0 0 60px',
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
          <VideoCameraOutlined style={{ marginRight: 8, color: '#5b4aff' }} />
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
              background: '#fff',
              border: '1px solid #e5e5e5',
              borderRadius: 12,
              padding: 40,
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
            <Title level={3} style={{ color: '#333', marginBottom: 8 }}>生成任务已启动！</Title>
            <Text style={{ color: '#999', display: 'block', marginBottom: 24 }}>
              数字人形象正在后台生成，通常需要 1~5 分钟，完成后状态将自动更新为"可用"。
            </Text>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <Button
                type="primary"
                size="large"
                onClick={() => navigate('/avatars')}
                style={{
                  background: '#5b4aff',
                  border: 'none',
                  borderRadius: 8,
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
                style={{ borderRadius: 8 }}
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
              strokeColor="#5b4aff"
            />
            <div style={{ marginTop: 24 }}>
              <Text style={{ color: '#666', fontSize: 16 }}>
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
            style={{ marginBottom: 24, borderRadius: 8 }}
          />
        )}

        {/* 主表单 */}
        {(step === 'upload' || step === 'error') && (
          <Form
            form={form}
            layout="vertical"
            initialValues={{ voice_id: DEFAULT_VOICE_ID }}
          >
            {/* 视频上传 */}
            <div
              style={{
                background: '#fff',
                borderRadius: 12,
                padding: 24,
                marginBottom: 24,
                border: '1px solid #e5e5e5',
              }}
            >
              <Title level={5} style={{ color: '#333', marginBottom: 16 }}>
                1. 上传人物视频
              </Title>
              <Text style={{ color: '#999', fontSize: 12, display: 'block', marginBottom: 16 }}>
                支持 MP4 / MOV / AVI 格式，视频时长建议 5~60 秒，确保视频中有清晰的正面人脸。
              </Text>

              {!videoFile ? (
                <Dragger
                  accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi"
                  beforeUpload={handleVideoChange}
                  showUploadList={false}
                  style={{
                    background: '#f5f5f5',
                    borderColor: '#ddd',
                    borderRadius: 8,
                  }}
                >
                  <p style={{ fontSize: 40, color: '#5b4aff' }}>
                    <InboxOutlined />
                  </p>
                  <p style={{ color: '#333', fontSize: 16, fontWeight: 500, margin: '8px 0 4px' }}>
                    点击或拖拽视频文件到此处
                  </p>
                  <p style={{ color: '#999', fontSize: 13 }}>
                    MP4 / MOV / AVI，最大 500MB
                  </p>
                </Dragger>
              ) : (
                <div style={{ position: 'relative' }}>
                  <video
                    src={videoPreview}
                    controls
                    style={{ width: '100%', borderRadius: 8, maxHeight: 280, objectFit: 'cover' }}
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
                background: '#fff',
                borderRadius: 12,
                padding: 24,
                border: '1px solid #e5e5e5',
              }}
            >
              <Title level={5} style={{ color: '#333', marginBottom: 16 }}>
                2. 配置形象信息
              </Title>

              <Form.Item
                label={<span style={{ color: '#666' }}>形象名称</span>}
                name="name"
                rules={[{ required: true, message: '请输入形象名称' }]}
              >
                <Input placeholder="例如：小雅" size="large" style={{ borderRadius: 8 }} />
              </Form.Item>

              <div style={{ marginBottom: 24 }}>
                <Text style={{ color: '#666', display: 'block', marginBottom: 8, fontSize: 14 }}>
                  语音引擎 (TTS)
                </Text>
                <div style={{
                  background: '#f5f5f5',
                  padding: '10px 16px',
                  borderRadius: 8,
                  color: '#333',
                  fontWeight: 500,
                  fontSize: 14
                }}>
                  Doubao TTS
                </div>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                  固定使用豆包语音合成，提供更自然的对话体验
                </Text>
              </div>

              <Form.Item
                label={
                  <span style={{ color: '#666' }}>
                    语音音色
                    <Tooltip title="点击试听按钮可预览音色效果">
                      <InfoCircleOutlined style={{ marginLeft: 4, color: '#999', fontSize: 12 }} />
                    </Tooltip>
                  </span>
                }
                name="voice_id"
                rules={[{ required: true, message: '请选择语音音色' }]}
                initialValue={DEFAULT_VOICE_ID}
              >
                <Space.Compact style={{ width: '100%' }}>
                  <Select
                    options={VOICE_OPTIONS}
                    value={selectedVoice}
                    onChange={(val) => {
                      setSelectedVoice(val);
                      setShowCustomInput(val === '__custom__');
                      form.setFieldValue('voice_id', val === '__custom__' ? customVoice : val);
                    }}
                    showSearch
                    optionFilterProp="label"
                    placeholder="选择音色"
                    style={{ flex: 1 }}
                    size="large"
                  />
                  <Button
                    icon={<SoundOutlined />}
                    onClick={() => handlePreviewVoice(selectedVoice)}
                    disabled={selectedVoice === '__custom__' || !selectedVoice || previewLoading}
                    loading={previewLoading}
                  >
                    试听
                  </Button>
                </Space.Compact>
              </Form.Item>

              {showCustomInput && (
                <div style={{ marginBottom: 24, marginLeft: 8 }}>
                  <Text style={{ color: '#666', fontSize: 14, display: 'block', marginBottom: 8 }}>
                    自定义 Voice ID
                  </Text>
                  <Input
                    placeholder="输入 Doubao Voice Type ID"
                    value={customVoice}
                    onChange={(e) => {
                      setCustomVoice(e.target.value);
                      form.setFieldValue('voice_id', e.target.value);
                    }}
                    style={{ borderRadius: 8 }}
                    size="large"
                  />
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                    完整音色列表请参考：
                    <a href="https://www.volcengine.com/docs/6561/1257544" target="_blank" rel="noopener noreferrer">
                      豆包语音音色列表
                    </a>
                  </Text>
                </div>
              )}
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
                  background: videoFile ? '#5b4aff' : undefined,
                  border: 'none',
                  borderRadius: 8,
                  height: 48,
                  paddingInline: 48,
                  fontSize: 16,
                  fontWeight: 500,
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
