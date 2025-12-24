import { RobotOutlined, UserOutlined } from '@ant-design/icons';
import { Bubble, Sender } from '@ant-design/x';
import { Avatar, Flex } from 'antd';
import { useState } from 'react';

export interface ChatMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
}

interface ChatSidebarProps {
    chatHistory: ChatMessage[];
    onSendMessage: (text: string) => void;
}

export default function ChatSidebar({ chatHistory, onSendMessage }: ChatSidebarProps) {
    const [value, setValue] = useState('');

    const handleSubmit = () => {
        if (!value.trim()) return;
        onSendMessage(value);
        setValue('');
    };

    return (
        <div className="w-80 bg-white border-l border-gray-200 flex flex-col h-full">
            <div className="p-4 border-b border-gray-200">
                <h2 className="text-gray-800 text-lg font-semibold m-0">聊天记录</h2>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
                <Flex vertical gap="middle">
                    {chatHistory.map((item, index) => (
                        <Bubble
                            key={index}
                            placement={item.role === 'user' ? 'end' : 'start'}
                            content={item.content}
                            avatar={
                                <Avatar
                                    icon={item.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                                    style={{ backgroundColor: item.role === 'user' ? '#1677ff' : '#52c41a' }}
                                />
                            }
                            styles={{
                                content: {
                                    backgroundColor: item.role === 'user' ? '#1677ff' : 'rgba(0, 0, 0, 0.06)',
                                    color: item.role === 'user' ? '#fff' : 'rgba(0, 0, 0, 0.88)',
                                }
                            }}
                        />
                    ))}
                </Flex>
            </div>

            <div className="p-4 border-t border-gray-200">
                <Sender
                    value={value}
                    onChange={setValue}
                    onSubmit={handleSubmit}
                    placeholder="输入消息..."
                />
            </div>
        </div>
    );
}
