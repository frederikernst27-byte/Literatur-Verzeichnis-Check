const { handleUpload } = require('@vercel/blob/client');

module.exports = async (request, response) => {
  if (request.method !== 'POST') {
    response.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const body = request.body;

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        return {
          allowedContentTypes: ['application/pdf'],
          addRandomSuffix: true,
          maximumSizeInBytes: 50 * 1024 * 1024,
        };
      },
      onUploadCompleted: async () => {},
    });

    response.status(200).json(jsonResponse);
  } catch (error) {
    response.status(400).json({ error: error.message });
  }
};
